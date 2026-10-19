import subprocess
import sys
from pathlib import Path

try:
    from .update_orders_from_txt import update_orders
    from .update_transactions import update_transactions
    from .update_inventory import update_inventory
    from .update_ppc import update_ppc
    from .update_business_reports import update_business_reports
    from .update_asin_economics import update_asin_economics
except ImportError:  # Supports direct execution from this directory.
    from update_orders_from_txt import update_orders
    from update_transactions import update_transactions
    from update_inventory import update_inventory
    from update_ppc import update_ppc
    from update_business_reports import update_business_reports
    from update_asin_economics import update_asin_economics


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def refresh_analytics():
    """Rebuild every dependent analytics mart after raw imports finish."""
    stages = (
        ("Stage 1 dimensions and fees", "materialize_stage1.py"),
        ("Stage 2 COGS and profitability", "seed_stage2_cogs.py"),
        ("Stage 3 PPC analytics", "materialize_stage3.py"),
    )
    for label, script in stages:
        print(f"\n--- Refreshing {label} ---")
        subprocess.run([sys.executable, script], cwd=PROJECT_ROOT, check=True)


def update_all():
    print("\n==============================")
    print("STARTING LITET DATABASE UPDATE")
    print("==============================\n")

    print("\n--- Updating orders ---")
    update_orders()

    print("\n--- Updating transactions ---")
    update_transactions()

    print("\n--- Updating inventory snapshots ---")
    update_inventory()

    print("\n--- Updating PPC ---")
    update_ppc()

    print("\n--- Updating business traffic ---")
    update_business_reports()

    print("\n--- Updating ASIN economics ---")
    update_asin_economics()

    refresh_analytics()

    print("\n==============================")
    print("LITET DATABASE UPDATE COMPLETE")
    print("==============================")


if __name__ == "__main__":
    update_all()
