"""
Quick script to add MBP-10 filters to remaining playbooks.

Updates:
- momentum_continuation.py
- opening_drive_reversal.py  
- ib_fade.py

Author: Nick Burner
Date: October 9, 2025
"""

import re
from pathlib import Path

# MBP-10 filter code to inject
MBP10_FILTER_CODE = """
        # ===================================================================
        # MBP-10 ORDER FLOW FILTERS (Week 2 Enhancement)
        # ===================================================================
        if mbp10_snapshot is not None:
            from orb_confluence.features.order_book_features import OrderBookFeatures
            ob_features = OrderBookFeatures()
            
            # Calculate OFI (Order Flow Imbalance)
            ofi = ob_features.order_flow_imbalance(mbp10_snapshot)
            
            # Calculate Depth Imbalance
            depth_imb = ob_features.depth_imbalance(mbp10_snapshot)
            
            # FILTER 1: OFI Confirmation
            # Require order flow to support direction
            if direction == Direction.LONG:
                if ofi < 0.3:  # Not enough buying pressure
                    logger.debug(
                        f"{self.name}: LONG rejected - insufficient buy flow "
                        f"(OFI={ofi:.3f} < 0.3)"
                    )
                    return None
            else:  # SHORT
                if ofi > -0.3:  # Not enough selling pressure
                    logger.debug(
                        f"{self.name}: SHORT rejected - insufficient sell flow "
                        f"(OFI={ofi:.3f} > -0.3)"
                    )
                    return None
            
            # FILTER 2: Depth Imbalance Confirmation
            # Require book depth to support direction
            if direction == Direction.LONG:
                if depth_imb < 0.2:  # Not enough bid support
                    logger.debug(
                        f"{self.name}: LONG rejected - insufficient depth support "
                        f"(depth={depth_imb:.3f} < 0.2)"
                    )
                    return None
            else:  # SHORT
                if depth_imb > -0.2:  # Not enough ask pressure
                    logger.debug(
                        f"{self.name}: SHORT rejected - insufficient depth pressure "
                        f"(depth={depth_imb:.3f} > -0.2)"
                    )
                    return None
            
            logger.info(
                f"{self.name}: {direction.value} entry CONFIRMED by order flow "
                f"(OFI={ofi:.3f}, Depth={depth_imb:.3f})"
            )
        # ===================================================================
"""

def update_playbook(file_path: Path, playbook_name: str):
    """Update a playbook file to include MBP-10 filters."""
    
    print(f"\n{'='*80}")
    print(f"Updating {playbook_name}")
    print(f"{'='*80}")
    
    content = file_path.read_text()
    
    # 1. Add mbp10_snapshot parameter to check_entry signature
    old_signature = """    def check_entry(
        self,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        regime: str,
        features: Dict[str, float],
        open_positions: List[Any],
    ) -> Optional[Signal]:"""
    
    new_signature = """    def check_entry(
        self,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        regime: str,
        features: Dict[str, float],
        open_positions: List[Any],
        mbp10_snapshot: Optional[Dict] = None,
    ) -> Optional[Signal]:"""
    
    if old_signature in content:
        content = content.replace(old_signature, new_signature)
        print("  ✅ Updated check_entry signature")
    else:
        print("  ⚠️  Signature already updated or not found")
    
    # 2. Find where to insert filter code
    # Look for pattern where direction is determined
    direction_patterns = [
        (r"(\n\s+)(direction = Direction\.LONG.*?\n)", "after_long"),
        (r"(\n\s+)(direction = Direction\.SHORT.*?\n)", "after_short"),
        (r"(\n\s+)(# Determine direction.*?direction = Direction\.\w+.*?\n)", "after_determine"),
    ]
    
    inserted = False
    for pattern, location in direction_patterns:
        matches = list(re.finditer(pattern, content, re.DOTALL))
        if matches:
            # Insert after last match
            last_match = matches[-1]
            insert_pos = last_match.end()
            
            # Only insert if not already there
            if "MBP-10 ORDER FLOW FILTERS" not in content:
                content = content[:insert_pos] + MBP10_FILTER_CODE + content[insert_pos:]
                print(f"  ✅ Inserted MBP-10 filters at {location}")
                inserted = True
                break
    
    if not inserted and "MBP-10 ORDER FLOW FILTERS" not in content:
        print("  ⚠️  Could not find insertion point automatically")
        print("  ⚠️  Manual update may be required")
    elif "MBP-10 ORDER FLOW FILTERS" in content:
        print("  ℹ️  MBP-10 filters already present")
    
    # Write back
    file_path.write_text(content)
    print(f"  ✅ Saved {file_path.name}")


def main():
    """Update all playbooks."""
    
    playbooks_dir = Path("orb_confluence/strategy/playbooks")
    
    playbooks_to_update = [
        ("momentum_continuation.py", "Momentum Continuation"),
        ("opening_drive_reversal.py", "Opening Drive Reversal"),
        ("ib_fade.py", "Initial Balance Fade"),
    ]
    
    for filename, name in playbooks_to_update:
        file_path = playbooks_dir / filename
        if file_path.exists():
            update_playbook(file_path, name)
        else:
            print(f"\n❌ File not found: {file_path}")
    
    print(f"\n{'='*80}")
    print("✅ ALL PLAYBOOKS UPDATED!")
    print(f"{'='*80}")
    print("\nNext step: Test and run backtest comparison")


if __name__ == "__main__":
    main()

