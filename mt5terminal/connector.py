import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# --- OS-Agnostic MT5 Import ---
try:
    import MetaTrader5 as mt5
except ImportError:
    from unittest.mock import MagicMock

    print(
        "WARNING: MetaTrader5 module not found. Using Mock object (Safe for local testing)."
    )
    mt5 = MagicMock()
# ------------------------------


class MT5DataClient:
    def __init__(self):
        try:
            load_dotenv()
            self.login = int(os.getenv("MT5_LOGIN"))
            self.password = os.getenv("MT5_PASSWORD")
            self.server = os.getenv("MT5_SERVER")
            self.timezone_str = os.getenv("MT5_TIMEZONE", "Etc/UTC")
            self.path = os.getenv("MT5_PATH")
        except (TypeError, ValueError) as e:
            raise ValueError(
                "Failed to load environment variables. Check your .env file and ensure MT5_LOGIN, MT5_PASSWORD, and MT5_SERVER are set correctly."
            ) from e

        if not mt5.initialize(path=self.path):
            raise RuntimeError(f"Initialisation error: {mt5.last_error()}")

        self.connected = True
        self.terminal_info = mt5.terminal_info()._asdict()

        try:
            self.authorised = mt5.login(
                self.login, password=self.password, server=self.server
            )
        except Exception as e:
            raise ValueError("Authorisation error")

        # Replaced pytz with Python's native zoneinfo
        self.timezone = ZoneInfo(self.timezone_str)
        self._initialisedAt = datetime.now()

    @property
    def total_symbols(self):
        return mt5.symbols_total() if self.connected else 0

    @property
    def timeframes(self):
        return {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }

    def get_targeted_symbols(self, symbol_list):
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        results = []
        for sym in symbol_list:
            mt5.symbol_select(sym, True)
            info = mt5.symbol_info(sym)
            if info is not None:
                results.append(info._asdict())

        if not results:
            raise ValueError("Failed to retrieve data for the provided symbols.")

        return results

    def get_symbol(self, symbol_name):
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        mt5.symbol_select(symbol_name, True)
        symbol = mt5.symbol_info(symbol_name)
        if symbol is None:
            raise ValueError(f"Failed to get symbol info for {symbol_name}")
        return symbol._asdict()

    def get_last_tick(self, symbol_name):
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        tick = mt5.symbol_info_tick(symbol_name)
        if tick is None:
            raise ValueError(f"Failed to get tick info for {symbol_name}")
        return tick._asdict()

    # --- Fast NumPy Array parsing replaces Pandas ---
    def _parse_mt5_array(self, array_data):
        """Helper to convert MT5 numpy structured arrays directly to list of dicts."""
        columns = array_data.dtype.names
        return [dict(zip(columns, row)) for row in array_data.tolist()]

    def get_ohlc_from(self, symbol_name, timeframe, from_date: datetime, count=1000):
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        utc_from = datetime(
            from_date.year,
            from_date.month,
            from_date.day,
            from_date.hour,
            from_date.minute,
            from_date.second,
            tzinfo=self.timezone,
        )
        rates = mt5.copy_rates_from(symbol_name, timeframe, utc_from, count)

        if rates is None or len(rates) == 0:
            raise ValueError(f"Failed to get OHLC data for {symbol_name}")

        return self._parse_mt5_array(rates)

    def get_ohlc_from_pos(self, symbol_name, timeframe, start_pos=0, count=100):
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        rates = mt5.copy_rates_from_pos(symbol_name, timeframe, start_pos, count)

        if rates is None or len(rates) == 0:
            raise ValueError(f"Failed to get OHLC data for {symbol_name}")

        return self._parse_mt5_array(rates)

    def get_ohlc_range(
        self, symbol_name, timeframe, from_date: datetime, to_date: datetime
    ):
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        utc_from = datetime(
            from_date.year,
            from_date.month,
            from_date.day,
            from_date.hour,
            from_date.minute,
            from_date.second,
            tzinfo=self.timezone,
        )
        utc_to = datetime(
            to_date.year,
            to_date.month,
            to_date.day,
            to_date.hour,
            to_date.minute,
            to_date.second,
            tzinfo=self.timezone,
        )

        rates = mt5.copy_rates_range(symbol_name, timeframe, utc_from, utc_to)

        if rates is None or len(rates) == 0:
            raise ValueError(f"Failed to get OHLC data for {symbol_name}")

        return self._parse_mt5_array(rates)

    def get_ticks_from(
        self, symbol_name, from_date: datetime, count=10000, flags=mt5.COPY_TICKS_ALL
    ):
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        utc_from = datetime(
            from_date.year,
            from_date.month,
            from_date.day,
            from_date.hour,
            from_date.minute,
            from_date.second,
            tzinfo=self.timezone,
        )
        ticks = mt5.copy_ticks_from(symbol_name, utc_from, count, flags)

        if ticks is None or len(ticks) == 0:
            raise ValueError(f"Failed to get ticks data for {symbol_name}")

        return self._parse_mt5_array(ticks)

    def get_ticks_range(
        self,
        symbol_name,
        from_date: datetime,
        to_date: datetime,
        flags=mt5.COPY_TICKS_ALL,
    ):
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        utc_from = datetime(
            from_date.year,
            from_date.month,
            from_date.day,
            from_date.hour,
            from_date.minute,
            from_date.second,
            tzinfo=self.timezone,
        )
        utc_to = datetime(
            to_date.year,
            to_date.month,
            to_date.day,
            to_date.hour,
            to_date.minute,
            to_date.second,
            tzinfo=self.timezone,
        )

        ticks = mt5.copy_ticks_range(symbol_name, utc_from, utc_to, flags)

        if ticks is None or len(ticks) == 0:
            raise ValueError(f"Failed to get ticks data for {symbol_name}")

        return self._parse_mt5_array(ticks)

    def get_account_info(self):
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")
        account_info = mt5.account_info()._asdict()
        if account_info is None:
            raise ValueError("Failed to get account info")
        return account_info

    def get_all_symbols(self, group="*"):
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")
        symbols = mt5.symbols_get(group=group)
        if symbols is None or len(symbols) == 0:
            raise ValueError("Failed to get symbols")
        return [symbol._asdict() for symbol in symbols]

    def get_last_error(self):
        return mt5.last_error()

    def is_connected(self):
        try:
            return mt5.terminal_info().connected
        except Exception:
            return False

    def shutdown(self):
        if self.connected:
            mt5.shutdown()
            self.connected = False

    # ----------------------------------------------------------------------
    # Trade Execution and Order Management Methods
    # ----------------------------------------------------------------------

    def get_open_positions(self, symbol=None):
        """Retrieve open positions, optionally filtered by symbol."""
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None:
            return []

        pos_list = []
        for pos in positions:
            p_dict = pos._asdict()

            # Fetch symbol info to get the contract size
            sym_info = mt5.symbol_info(p_dict["symbol"])
            contract_size = sym_info.trade_contract_size if sym_info else 100000.0

            # Calculate Nominal Value: Volume * Contract Size * Current Price
            p_dict["nominal_value"] = (
                p_dict["volume"] * contract_size * p_dict["price_current"]
            )

            # Calculate Exact Margin
            margin = mt5.order_calc_margin(
                p_dict["type"], p_dict["symbol"], p_dict["volume"], p_dict["price_open"]
            )
            p_dict["margin"] = margin if margin is not None else 0.0
            pos_list.append(p_dict)

        return pos_list

    def get_pending_orders(self, symbol=None):
        """Retrieve pending orders, optionally filtered by symbol."""
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        if symbol:
            orders = mt5.orders_get(symbol=symbol)
        else:
            orders = mt5.orders_get()

        if orders is None:
            return []

        return [order._asdict() for order in orders]

    def execute_market_order(
        self,
        symbol: str,
        volume: float,
        order_type: int,
        deviation: int = 20,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        magic: int = 1000,
    ):
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        mt5.symbol_select(symbol, True)
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            raise ValueError(
                f"Symbol {symbol} not found or not visible in Market Watch"
            )

        # Normalize Volume (AAPL needs 1.0, Forex needs 0.01)
        v_min = symbol_info.volume_min
        v_step = symbol_info.volume_step

        # 1. Safety Check: Don't silently buy 1.0 lots if user asked for 0.01!
        if float(volume) < v_min:
            raise ValueError(
                f"Minimum volume for {symbol} is {v_min}. You requested {volume}."
            )

        normalized_volume = round(float(volume) / v_step) * v_step

        # 2. Fix the missing attribute bug (Use raw bitwise integers)
        # 1 = FOK, 2 = IOC
        allowed_modes = symbol_info.filling_mode
        if allowed_modes & 2:
            filling_mode = mt5.ORDER_FILLING_IOC
        elif allowed_modes & 1:
            filling_mode = mt5.ORDER_FILLING_FOK
        else:
            filling_mode = mt5.ORDER_FILLING_RETURN

        price = (
            mt5.symbol_info_tick(symbol).ask
            if order_type == mt5.ORDER_TYPE_BUY
            else mt5.symbol_info_tick(symbol).bid
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(normalized_volume),
            "type": order_type,
            "price": price,
            "sl": float(stop_loss),
            "tp": float(take_profit),
            "deviation": deviation,
            "magic": magic,
            "comment": "MarketDash Pro",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        result = mt5.order_send(request)
        if result is None:
            raise RuntimeError(f"Order send failed. MT5 error: {mt5.last_error()}")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(
                f"Order rejected. Retcode: {result.retcode}, Comment: {result.comment}"
            )

        return result._asdict()

    def close_position(self, ticket: int):
        """Close a specific open position by its ticket ID."""
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        # Get the specific position
        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            raise ValueError(f"Position with ticket #{ticket} not found.")

        pos = positions[0]._asdict()
        symbol = pos["symbol"]
        volume = pos["volume"]
        pos_type = pos["type"]

        mt5.symbol_select(symbol, True)
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            raise ValueError(f"Symbol {symbol} info unavailable")

        # Dynamically determine the supported filling mode
        allowed_modes = symbol_info.filling_mode
        if allowed_modes & 2:
            filling_mode = mt5.ORDER_FILLING_IOC
        elif allowed_modes & 1:
            filling_mode = mt5.ORDER_FILLING_FOK
        else:
            filling_mode = mt5.ORDER_FILLING_RETURN

        # Opposite order type to close
        close_type = (
            mt5.ORDER_TYPE_SELL
            if pos_type == mt5.POSITION_TYPE_BUY
            else mt5.ORDER_TYPE_BUY
        )
        price = (
            mt5.symbol_info_tick(symbol).bid
            if close_type == mt5.ORDER_TYPE_SELL
            else mt5.symbol_info_tick(symbol).ask
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 1000,
            "comment": "MarketDash Manual Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        result = mt5.order_send(request)
        if result is None:
            raise RuntimeError(f"Order send failed. MT5 error: {mt5.last_error()}")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(
                f"Order rejected. Retcode: {result.retcode}, Comment: {result.comment}"
            )

        return result._asdict()

    def flatten_all_positions(self):
        """Emergency method to close all open positions across all symbols."""
        positions = self.get_open_positions()
        results = []
        errors = []

        for pos in positions:
            symbol = pos["symbol"]
            volume = pos["volume"]
            pos_type = pos["type"]
            ticket = pos["ticket"]

            # Make sure symbol info is accessible for filling mode and prices
            mt5.symbol_select(symbol, True)
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                errors.append(
                    {"ticket": ticket, "error": f"Symbol {symbol} info unavailable"}
                )
                continue

            # Dynamically determine the supported filling mode for this specific asset
            allowed_modes = symbol_info.filling_mode
            if allowed_modes & 2:
                filling_mode = mt5.ORDER_FILLING_IOC
            elif allowed_modes & 1:
                filling_mode = mt5.ORDER_FILLING_FOK
            else:
                filling_mode = mt5.ORDER_FILLING_RETURN

            # Opposite order type to close
            close_type = (
                mt5.ORDER_TYPE_SELL
                if pos_type == mt5.POSITION_TYPE_BUY
                else mt5.ORDER_TYPE_BUY
            )
            price = (
                mt5.symbol_info_tick(symbol).bid
                if close_type == mt5.ORDER_TYPE_SELL
                else mt5.symbol_info_tick(symbol).ask
            )

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": close_type,
                "position": ticket,
                "price": price,
                "deviation": 20,
                "magic": 1000,
                "comment": "MarketDash Panic Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }

            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                results.append(result._asdict())
            else:
                errors.append(
                    {
                        "ticket": ticket,
                        "error": result.comment if result else str(mt5.last_error()),
                    }
                )

        return {"closed": results, "failed": errors}

    def get_trade_history(self, days=30):
        """Retrieve closed trades (deals) from the last X days."""
        if not self.connected:
            raise RuntimeError("MT5 terminal not connected")

        # MT5 expects naive datetimes representing UTC for its history queries
        date_to = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)  # noqa: UP017
        date_from = date_to - timedelta(days=days + 1)

        deals = mt5.history_deals_get(date_from, date_to)
        if deals is None:
            return []

        history = []
        for deal in deals:
            d_dict = deal._asdict()
            # We only want deals that CLOSED a position (Entry Out or InOut)
            if d_dict.get("entry") in [mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT]:
                history.append(d_dict)

        # Sort by time descending (newest first)
        history.sort(key=lambda x: x["time"], reverse=True)
        return history

    def __repr__(self):
        return f"MT5DataClient(login={self.login}, server={self.server}, connected={self.connected}, authorised={self.authorised}, timezone={self.timezone})"

    def __str__(self):
        return self.__repr__()
