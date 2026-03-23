"""Command-line interface for Aroma Lab."""

import argparse
from pathlib import Path

# Default data directory
DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data" / "aromachemicals"


def _handle_db_command(args):
    """Handle database subcommands."""
    from src.database import AromachemicalDB, load_from_csv
    from src.models import OdorFamily, Volatility

    if args.db_command == "stats":
        db = AromachemicalDB(args.data_dir)
        stats = db.stats()

        print(f"\nAromachemical Database Statistics")
        print("=" * 40)
        print(f"Total compounds: {stats['total_count']}")
        print(f"With cost data: {stats['with_cost']}")
        print(f"IFRA restricted: {stats['ifra_restricted']}")

        print(f"\nBy Volatility:")
        for vol, count in sorted(stats['by_volatility'].items()):
            print(f"  {vol}: {count}")

        print(f"\nBy Odor Family:")
        for fam, count in sorted(stats['by_family'].items(), key=lambda x: -x[1]):
            print(f"  {fam}: {count}")

    elif args.db_command == "search":
        db = AromachemicalDB(args.data_dir)

        # Parse filters
        odor_family = None
        if args.family:
            try:
                odor_family = OdorFamily(args.family.lower())
            except ValueError:
                print(f"Unknown odor family: {args.family}")
                return

        volatility = None
        if args.volatility:
            volatility = Volatility(args.volatility)

        results = db.search(
            query=args.query,
            odor_family=odor_family,
            volatility=volatility,
        )

        if not results:
            print(f"No results found for '{args.query}'")
        else:
            print(f"\nFound {len(results)} results for '{args.query}':")
            print("-" * 60)
            for ac in results[:20]:  # Limit to 20 results
                vol = ac.volatility.value if ac.volatility else "?"
                families = ", ".join(f.value for f in ac.odor_families) if ac.odor_families else "-"
                print(f"  [{ac.cas_number}] {ac.name}")
                print(f"    {vol.upper()} | {families}")
                if ac.odor_description:
                    print(f"    {ac.odor_description[:60]}...")
                print()

    elif args.db_command == "show":
        db = AromachemicalDB(args.data_dir)

        # Try CAS first, then name
        ac = db.get_by_cas(args.cas_or_name) or db.get_by_name(args.cas_or_name)

        if not ac:
            print(f"Aromachemical not found: {args.cas_or_name}")
            return

        print(f"\n{ac.name}")
        print("=" * len(ac.name))
        print(f"CAS Number: {ac.cas_number}")
        if ac.iupac_name:
            print(f"IUPAC Name: {ac.iupac_name}")
        if ac.molecular_formula:
            print(f"Formula: {ac.molecular_formula} (MW: {ac.molecular_weight})")
        print()
        print(f"Odor: {ac.odor_description}")
        if ac.odor_families:
            print(f"Families: {', '.join(f.value for f in ac.odor_families)}")
        if ac.volatility:
            print(f"Volatility: {ac.volatility.value}")
        if ac.boiling_point_c:
            print(f"Boiling Point: {ac.boiling_point_c}°C")
        print()
        if ac.natural_occurrence:
            print(f"Natural occurrence: {', '.join(ac.natural_occurrence)}")
        if ac.ifra_restricted:
            print(f"IFRA Restricted: Yes (max {ac.max_usage_percent}%)")
        if ac.cost_per_kg_usd:
            print(f"Cost: ${ac.cost_per_kg_usd}/kg")

    elif args.db_command == "import":
        chemicals = load_from_csv(args.csv_file)
        print(f"Loaded {len(chemicals)} chemicals from {args.csv_file}")

        if args.output:
            db = AromachemicalDB()
            for ac in chemicals:
                db.add(ac)
            db.save(args.output)
            print(f"Saved to {args.output}")
        else:
            for ac in chemicals[:5]:
                print(f"  - {ac.name} ({ac.cas_number})")
            if len(chemicals) > 5:
                print(f"  ... and {len(chemicals) - 5} more")

    else:
        print("Use: aroma-lab db {stats|search|show|import}")


def _handle_parse_command(args):
    """Parse a GC-MS data file and display results."""
    import json
    from src.parsers.nist_parser import NISTParser
    from src.parsers.shimadzu_parser import ShimadzuParser
    from src.parsers.agilent_parser import AgilentParser
    from src.parsers.csv_parser import CSVParser
    from src.parsers.mzml_parser import MzMLParser

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        return

    # Auto-detect format
    parsers = [NISTParser(), ShimadzuParser(), AgilentParser(), CSVParser(), MzMLParser()]
    parser = None
    for p in parsers:
        if p.can_parse(file_path):
            parser = p
            break

    if not parser:
        print(f"Error: Could not detect format for {file_path.name}")
        print("Supported formats: NIST (.MSP), Shimadzu (.txt), Agilent (.csv/.txt), CSV, mzML")
        return

    print(f"Detected format: {parser.__class__.__name__.replace('Parser', '')}")
    profile = parser.parse(file_path)

    print(f"\nProfile: {profile.name}")
    print(f"Peaks found: {len(profile.peaks)}")
    print("-" * 70)
    print(f"{'RT (min)':>10}  {'Area %':>8}  {'CAS':>14}  Compound")
    print("-" * 70)
    for peak in sorted(profile.peaks, key=lambda p: p.area_percent, reverse=True):
        cas = peak.cas_number or "-"
        name = peak.compound_name or "Unknown"
        print(f"{peak.retention_time:>10.2f}  {peak.area_percent:>8.2f}  {cas:>14}  {name}")

    if args.output:
        data = {
            "name": profile.name,
            "peaks": [
                {
                    "retention_time": p.retention_time,
                    "area_percent": p.area_percent,
                    "cas_number": p.cas_number,
                    "compound_name": p.compound_name,
                }
                for p in profile.peaks
            ],
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"\nSaved to {args.output}")


def _handle_formulate_command(args):
    """Generate a formula from a GC-MS profile."""
    import json
    from src.models import NaturalProfile, GCMSPeak
    from src.database import AromachemicalDB
    from src.matching.matcher import AromachemicalMatcher
    from src.formulator.engine import FormulatorEngine

    profile_path = Path(args.profile)
    if not profile_path.exists():
        print(f"Error: Profile not found: {profile_path}")
        return

    with open(profile_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Build NaturalProfile from JSON
    peaks = [
        GCMSPeak(
            retention_time=p.get("retention_time", 0),
            area_percent=p.get("area_percent", 0),
            cas_number=p.get("cas_number"),
            compound_name=p.get("compound_name"),
        )
        for p in data.get("peaks", data.get("compounds", []))
    ]
    profile = NaturalProfile(
        name=data.get("name", profile_path.stem),
        peaks=peaks,
    )

    # Load DB and build matcher
    db = AromachemicalDB(DEFAULT_DATA_DIR)
    chemicals = list(db.get_all())
    matcher = AromachemicalMatcher(chemicals)
    engine = FormulatorEngine(matcher)

    formula_name = args.name or f"{profile.name} Recreation"
    formula = engine.formulate(profile, name=formula_name)

    print(f"\nFormula: {formula.name}")
    print(f"Based on: {len(peaks)} peaks")
    print("=" * 60)

    if formula.ingredients:
        print(f"\n{'Ingredient':<35} {'%':>8}  {'Volatility':<10}")
        print("-" * 60)
        for ing in sorted(formula.ingredients, key=lambda i: i.percentage, reverse=True):
            vol = ing.aromachemical.volatility.value if ing.aromachemical and ing.aromachemical.volatility else "-"
            name = ing.aromachemical.name if ing.aromachemical else ing.cas_number or "Unknown"
            print(f"  {name:<33} {ing.percentage:>7.2f}%  {vol:<10}")
        total = sum(i.percentage for i in formula.ingredients)
        print("-" * 60)
        print(f"  {'Total':<33} {total:>7.2f}%")

    if hasattr(formula, 'fidelity_score') and formula.fidelity_score:
        print(f"\nFidelity score: {formula.fidelity_score:.1%}")

    if args.output:
        out_data = {
            "name": formula.name,
            "ingredients": [
                {
                    "name": i.aromachemical.name if i.aromachemical else "Unknown",
                    "cas_number": i.aromachemical.cas_number if i.aromachemical else i.cas_number,
                    "percentage": i.percentage,
                }
                for i in formula.ingredients
            ],
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2)
        print(f"\nSaved to {args.output}")


def _handle_compare_command(args):
    """Compare two formulas or profiles."""
    import json

    for f in [args.file_a, args.file_b]:
        if not f.exists():
            print(f"Error: File not found: {f}")
            return

    with open(args.file_a, "r", encoding="utf-8") as f:
        data_a = json.load(f)
    with open(args.file_b, "r", encoding="utf-8") as f:
        data_b = json.load(f)

    name_a = data_a.get("name", args.file_a.stem)
    name_b = data_b.get("name", args.file_b.stem)

    # Build composition maps (CAS -> percentage)
    def extract_compounds(data):
        compounds = {}
        # Handle formula format (ingredients)
        for ing in data.get("ingredients", []):
            cas = ing.get("cas_number", ing.get("cas", ""))
            if cas:
                compounds[cas] = {
                    "name": ing.get("name", "Unknown"),
                    "pct": ing.get("percentage", ing.get("area_percent", 0)),
                }
        # Handle profile format (peaks/compounds)
        for p in data.get("peaks", data.get("compounds", [])):
            cas = p.get("cas_number", p.get("cas", ""))
            if cas:
                compounds[cas] = {
                    "name": p.get("compound_name", p.get("name", "Unknown")),
                    "pct": p.get("area_percent", p.get("percentage", 0)),
                }
        return compounds

    comp_a = extract_compounds(data_a)
    comp_b = extract_compounds(data_b)

    all_cas = set(comp_a.keys()) | set(comp_b.keys())
    shared = set(comp_a.keys()) & set(comp_b.keys())
    only_a = set(comp_a.keys()) - set(comp_b.keys())
    only_b = set(comp_b.keys()) - set(comp_a.keys())

    print(f"\nComparing: {name_a} vs {name_b}")
    print("=" * 70)
    print(f"Compounds in {name_a}: {len(comp_a)}")
    print(f"Compounds in {name_b}: {len(comp_b)}")
    print(f"Shared: {len(shared)} | Only in A: {len(only_a)} | Only in B: {len(only_b)}")

    if shared:
        print(f"\n{'Shared Compounds':<30} {name_a:>10} {name_b:>10}  {'Diff':>8}")
        print("-" * 65)
        for cas in sorted(shared, key=lambda c: abs(comp_a[c]["pct"] - comp_b[c]["pct"]), reverse=True):
            name = comp_a[cas]["name"]
            pct_a = comp_a[cas]["pct"]
            pct_b = comp_b[cas]["pct"]
            diff = pct_b - pct_a
            sign = "+" if diff > 0 else ""
            print(f"  {name:<28} {pct_a:>9.2f}% {pct_b:>9.2f}%  {sign}{diff:>6.2f}%")

    if only_a:
        print(f"\nOnly in {name_a}:")
        for cas in sorted(only_a, key=lambda c: comp_a[c]["pct"], reverse=True):
            print(f"  {comp_a[cas]['name']:<30} {comp_a[cas]['pct']:>7.2f}%")

    if only_b:
        print(f"\nOnly in {name_b}:")
        for cas in sorted(only_b, key=lambda c: comp_b[c]["pct"], reverse=True):
            print(f"  {comp_b[cas]['name']:<30} {comp_b[cas]['pct']:>7.2f}%")

    # Similarity score (Jaccard on compounds + weighted overlap)
    if all_cas:
        jaccard = len(shared) / len(all_cas)
        # Weighted similarity on shared compounds
        if shared:
            total_pct = sum(comp_a[c]["pct"] + comp_b[c]["pct"] for c in shared)
            total_diff = sum(abs(comp_a[c]["pct"] - comp_b[c]["pct"]) for c in shared)
            weighted = 1 - (total_diff / total_pct) if total_pct > 0 else 0
            similarity = 0.5 * jaccard + 0.5 * weighted
        else:
            similarity = 0
        print(f"\nOverall similarity: {similarity:.1%}")



    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Aroma Lab - Fragrance formulator using GC-MS data"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Database commands
    db_parser = subparsers.add_parser("db", help="Database operations")
    db_subparsers = db_parser.add_subparsers(dest="db_command")

    db_stats = db_subparsers.add_parser("stats", help="Show database statistics")
    db_stats.add_argument("-d", "--data-dir", type=Path, default=DEFAULT_DATA_DIR)

    db_search = db_subparsers.add_parser("search", help="Search aromachemicals")
    db_search.add_argument("query", help="Search query")
    db_search.add_argument("-d", "--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    db_search.add_argument("-f", "--family", help="Filter by odor family")
    db_search.add_argument("-v", "--volatility", choices=["top", "heart", "base"])

    db_show = db_subparsers.add_parser("show", help="Show aromachemical details")
    db_show.add_argument("cas_or_name", help="CAS number or name")
    db_show.add_argument("-d", "--data-dir", type=Path, default=DEFAULT_DATA_DIR)

    db_import = db_subparsers.add_parser("import", help="Import from CSV")
    db_import.add_argument("csv_file", type=Path, help="CSV file to import")
    db_import.add_argument("-o", "--output", type=Path, help="Output JSON file")

    # Parse command
    parse_parser = subparsers.add_parser("parse", help="Parse a GC-MS data file")
    parse_parser.add_argument("file", type=Path, help="Path to GC-MS data file")
    parse_parser.add_argument("-o", "--output", type=Path, help="Output file for parsed data")

    # Formulate command
    form_parser = subparsers.add_parser("formulate", help="Generate a formula from GC-MS profile")
    form_parser.add_argument("profile", type=Path, help="Path to profile JSON file")
    form_parser.add_argument("-n", "--name", help="Name for the formula")
    form_parser.add_argument("-o", "--output", type=Path, help="Output file for formula")

    # Compare command
    comp_parser = subparsers.add_parser("compare", help="Compare two formulas or profiles")
    comp_parser.add_argument("file_a", type=Path, help="First file")
    comp_parser.add_argument("file_b", type=Path, help="Second file")

    # Variations command
    var_parser = subparsers.add_parser("variations", help="Show variations of a natural")
    var_parser.add_argument("natural", help="Name of natural (e.g., 'rose oil')")

    args = parser.parse_args()

    if args.command == "db":
        _handle_db_command(args)

    elif args.command == "parse":
        _handle_parse_command(args)

    elif args.command == "formulate":
        _handle_formulate_command(args)

    elif args.command == "compare":
        _handle_compare_command(args)

    elif args.command == "variations":
        from src.variations import VariationDatabase
        db = VariationDatabase()
        variations = db.get_variations(args.natural)

        if not variations:
            print(f"No variations found for '{args.natural}'")
        else:
            print(f"\nVariations of {args.natural}:")
            print("-" * 50)
            for var in variations:
                print(f"\n{var.variation_name}")
                if var.botanical_name:
                    print(f"  Botanical: {var.botanical_name}")
                if var.region:
                    print(f"  Region: {var.region}")
                if var.character_notes:
                    print(f"  Character: {', '.join(var.character_notes)}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
