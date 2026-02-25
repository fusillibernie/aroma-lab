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


def main():
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
        print(f"Parsing {args.file}...")
        # TODO: Implement parsing

    elif args.command == "formulate":
        print(f"Generating formula from {args.profile}...")
        # TODO: Implement formulation

    elif args.command == "compare":
        print(f"Comparing {args.file_a} and {args.file_b}...")
        # TODO: Implement comparison

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
