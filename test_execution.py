import MetaTrader5 as mt5

from mt5terminal.connector import MT5DataClient


def test_trade():
    client = MT5DataClient()
    print(f"Connected to {client.terminal_info.get('company')} Demo")

    # 1. Check Balance
    account = client.get_account_info()
    print(f"Demo Balance: {account['balance']} {account['currency']}")

    # 2. Execute a 0.01 Micro-Lot BUY on EURUSD
    print("\nExecuting BUY order...")
    try:
        result = client.execute_market_order(
            symbol="EURUSD", volume=0.01, order_type=mt5.ORDER_TYPE_BUY
        )
        print(f"SUCCESS! Ticket: {result['order']}")
    except Exception as e:
        print(f"Order Failed: {e}")

    # 3. Check Open Positions
    positions = client.get_open_positions()
    print(f"\nOpen Positions: {len(positions)}")
    for pos in positions:
        print(
            f"Ticket {pos['ticket']} | {pos['symbol']} | {pos['volume']} Lots | Profit: {pos['profit']}"
        )

    # 4. Test the Panic Button (Flatten All)
    print("\nFlattening all positions...")
    flatten_result = client.flatten_all_positions()
    print(
        f"Closed: {len(flatten_result['closed'])}, Failed: {len(flatten_result['failed'])}"
    )

    client.shutdown()


if __name__ == "__main__":
    test_trade()
