import sqlite3
from datetime import datetime, timedelta
from config import settings

def verify_database():
    """Verify that swaps are being logged to the database"""
    try:
        conn = sqlite3.connect(settings.db_path)
        cursor = conn.cursor()
        
        # Count total swaps
        cursor.execute("SELECT COUNT(*) FROM dex_swaps")
        total_swaps = cursor.fetchone()[0]
        
        # Count swaps in last 5 minutes
        five_min_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
        cursor.execute("""
            SELECT COUNT(*) FROM dex_swaps 
            WHERE timestamp > ?
        """, (five_min_ago,))
        recent_swaps = cursor.fetchone()[0]
        
        # Get latest 5 swaps
        cursor.execute("""
            SELECT timestamp, router, token_in, token_out, amount_in, tx_hash
            FROM dex_swaps
            ORDER BY timestamp DESC
            LIMIT 5
        """)
        latest_swaps = cursor.fetchall()
        
        # Count new pools
        cursor.execute("SELECT COUNT(*) FROM new_pools")
        total_pools = cursor.fetchone()[0]
        
        print("=" * 60)
        print("📊 DATABASE VERIFICATION REPORT")
        print("=" * 60)
        print(f"✅ Total Swaps Logged: {total_swaps}")
        print(f"✅ Swaps (last 5 min): {recent_swaps}")
        print(f"✅ Total Pools Created: {total_pools}")
        print()
        print("📝 Latest 5 Swaps:")
        for swap in latest_swaps:
            timestamp, router, token_in, token_out, amount_in, tx_hash = swap
            print(f"   {timestamp[:19]} | {router} | {token_in}→{token_out} | {amount_in:.4f} ETH | {tx_hash[:10]}...")
        print("=" * 60)
        
        conn.close()
        
        if total_swaps > 0:
            print("✅ DATA PIPELINE VERIFIED - Swaps are being persisted!")
        else:
            print("⚠️  WARNING: No swaps found in database")
            
    except Exception as e:
        print(f"❌ Database verification failed: {e}")

if __name__ == "__main__":
    verify_database()
