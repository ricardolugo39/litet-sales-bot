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


def refresh_ppc_analytics():
    """Rebuild the clean PPC marts after a successful raw PPC import."""
    print("\n--- Refreshing PPC analytics ---")
    subprocess.run(
        [sys.executable, "materialize_stage3.py"],
        cwd=PROJECT_ROOT,
        check=True,
    )


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
    ppc_updated = update_ppc()

    print("\n--- Updating business traffic ---")
    update_business_reports()

    print("\n--- Updating ASIN economics ---")
    update_asin_economics()

    if ppc_updated:
        refresh_ppc_analytics()

    print("\n==============================")
    print("LITET DATABASE UPDATE COMPLETE")
    print("==============================")


if __name__ == "__main__":
    update_all()
