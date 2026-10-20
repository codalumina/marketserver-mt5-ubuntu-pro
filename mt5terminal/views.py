import csv
import os
import platform
import shutil
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .connector import MT5DataClient

# --- OS-Agnostic MT5 Import ---
try:
    import MetaTrader5 as mt5
except ImportError:
    from unittest.mock import MagicMock

    mt5 = MagicMock()
# ------------------------------

load_dotenv()

# Centralized Timezone Configuration
BROKER_TZ = ZoneInfo(os.getenv("MT5_TIMEZONE", "Etc/UTC"))


@api_view(["GET"])
def server_stat(request):
    """Retrieve comprehensive MetaTrader 5 and physical server statistics."""
    client = None
    try:
        client = MT5DataClient()
        terminal_info = client.terminal_info
        account_info = client.get_account_info()

        total_positions = (
            mt5.positions_total() if mt5.positions_total() is not None else 0
        )
        total_orders = mt5.orders_total() if mt5.orders_total() is not None else 0

        account_name = account_info.get("name", "Unknown")
        name_initials = (
            "".join([part[0] for part in account_name.split()])
            if account_name
            else "Unknown"
        )

        mt5_stats = {
            "connected": terminal_info.get("connected", False),
            "broker": account_info.get("company", "Unknown"),
            "server": account_info.get("server", "Unknown"),
            "account_name_initials": name_initials,
            "leverage": account_info.get("leverage", 0),
            "ping": terminal_info.get("ping_last", 0),
            "build": terminal_info.get("build", 0),
            "account_currency": account_info.get("currency", ""),
            "balance": account_info.get("balance", 0.0),
            "equity": account_info.get("equity", 0.0),
            "floating_profit": account_info.get("profit", 0.0),
            "margin_free": account_info.get("margin_free", 0.0),
            "margin_level_pct": account_info.get("margin_level", 0.0),
            "trade_allowed_by_broker": account_info.get("trade_allowed", False),
            "algo_trading_allowed": terminal_info.get("trade_allowed", False),
            "open_positions_count": total_positions,
            "pending_orders_count": total_orders,
        }

        os_stats = {
            "python_architecture": platform.architecture()[0],
            "wine_version": "Active",
        }

        try:
            with open("Z:/proc/meminfo", "r") as f:
                meminfo = f.readlines()
                total_mb = int(meminfo[0].split()[1]) / 1024
                available_mb = int(meminfo[2].split()[1]) / 1024
                os_stats["ram_total_mb"] = round(total_mb, 2)
                os_stats["ram_available_mb"] = round(available_mb, 2)
                os_stats["ram_used_mb"] = round(total_mb - available_mb, 2)

            with open("Z:/proc/loadavg", "r") as f:
                os_stats["cpu_load_avg"] = f.read().split()[:3]

            with open("Z:/proc/uptime", "r") as f:
                uptime_seconds = float(f.readline().split()[0])
                os_stats["uptime_days"] = round(uptime_seconds / 86400, 2)
                os_stats["uptime_hours"] = round(uptime_seconds / 3600, 2)

            with open("Z:/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
                os_stats["cpu_cores"] = cpuinfo.count("processor\t:")
                model_lines = [
                    line for line in cpuinfo.split("\n") if "model name" in line
                ]
                os_stats["cpu_model"] = (
                    model_lines[0].split(":")[1].strip()
                    if model_lines
                    else "Unknown CPU"
                )

            disk = shutil.disk_usage("Z:/")
            os_stats["disk_total_gb"] = round(disk.total / (1024**3), 2)
            os_stats["disk_free_gb"] = round(disk.free / (1024**3), 2)

        except Exception as e:
            os_stats["linux_read_error"] = (
                f"Could not read native Linux stats: {str(e)}"
            )

        return Response(
            {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mt5": mt5_stats,
                "server": os_stats,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {
                "status": "error",
                "error_message": f"Unexpected error: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    finally:
        if client is not None:
            client.shutdown()


@api_view(["GET"])
def recent_price_action(request):
    """Retrieve the most recent OHLC price action data for a specific symbol."""
    client = None
    try:
        symbol = request.query_params.get("symbol")
        timeframe_str = request.query_params.get("timeframe")

        try:
            count = int(request.query_params.get("count", 100))
        except ValueError:
            return Response(
                {"error": "'count' parameter must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not symbol or not timeframe_str:
            return Response(
                {"error": "Missing required parameters: symbol, timeframe"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = MT5DataClient()
        tf_map = client.timeframes
        tf_constant = tf_map.get(timeframe_str.upper())

        if tf_constant is None:
            return Response(
                {"error": f"Invalid timeframe. Valid options: {list(tf_map.keys())}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        price_action = client.get_ohlc_from_pos(
            symbol_name=symbol, start_pos=0, count=count, timeframe=tf_constant
        )

        for ohlc in price_action:
            # 1. Read MT5 timestamp exactly as emitted (treating as naive UTC temporarily to strip OS timezone)
            naive_dt = datetime.fromtimestamp(ohlc["time"], tz=timezone.utc).replace(
                tzinfo=None
            )

            # 2. Assign the actual Broker Timezone
            broker_aware_dt = naive_dt.replace(tzinfo=BROKER_TZ)

            # 3. Convert safely to true UTC
            utc_dt = broker_aware_dt.astimezone(timezone.utc)

            ohlc["time"] = int(utc_dt.timestamp())
            ohlc["iso_time"] = utc_dt.isoformat()

        return Response(
            {
                "symbol": symbol,
                "timeframe": timeframe_str.upper(),
                "count": len(price_action),
                "price_action": price_action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=status.HTTP_200_OK,
        )

    except ValueError as e:
        return Response(
            {"error": f"Invalid input or no data available: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        return Response(
            {"error": f"Unexpected error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    finally:
        if client is not None:
            client.shutdown()


@api_view(["GET"])
def historical_price_range(request):
    """Retrieve historical OHLC data for a strict date range (Quant Data Builder)."""
    client = None
    try:
        symbol = request.query_params.get("symbol")
        timeframe_str = request.query_params.get("timeframe")
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        if not all([symbol, timeframe_str, start_date_str, end_date_str]):
            return Response(
                {
                    "error": "Missing required parameters: symbol, timeframe, start_date, end_date"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse ISO 8601 strings to python datetime objects
        start_dt = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))

        client = MT5DataClient()
        tf_map = client.timeframes
        tf_constant = tf_map.get(timeframe_str.upper())

        if tf_constant is None:
            return Response(
                {"error": f"Invalid timeframe. Valid options: {list(tf_map.keys())}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        price_action = client.get_ohlc_range(
            symbol_name=symbol,
            timeframe=tf_constant,
            from_date=start_dt,
            to_date=end_dt,
        )

        for ohlc in price_action:
            # 1. Read MT5 timestamp exactly as emitted
            naive_dt = datetime.fromtimestamp(ohlc["time"], tz=timezone.utc).replace(
                tzinfo=None
            )
            # 2. Assign the actual Broker Timezone
            broker_aware_dt = naive_dt.replace(tzinfo=BROKER_TZ)
            # 3. Convert safely to true UTC
            utc_dt = broker_aware_dt.astimezone(timezone.utc)

            ohlc["time"] = int(utc_dt.timestamp())
            ohlc["iso_time"] = utc_dt.isoformat()

        return Response(
            {
                "symbol": symbol,
                "timeframe": timeframe_str.upper(),
                "count": len(price_action),
                "price_action": price_action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=status.HTTP_200_OK,
        )

    except ValueError as e:
        return Response(
            {"error": f"Invalid input or no data available: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        return Response(
            {"error": f"Unexpected error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    finally:
        if client is not None:
            client.shutdown()


@api_view(["GET"])
def all_symbols(request):
    """Retrieve detailed metadata for all available trading symbols."""
    client = None
    try:
        client = MT5DataClient()
        symbols = client.get_all_symbols()

        fields = [
            "name",
            "description",
            "exchange",
            "isin",
            "digits",
            "point",
            "volume_min",
            "volume_step",
            "volume_max",
            "trade_contract_size",
        ]
        data = []

        for sym in symbols:
            sym_data = {}
            sym_meta = sym.get("path", "").split("\\")
            sym_data["class"] = sym_meta[1] if len(sym_meta) > 1 else "Unknown"
            sym_data["group"] = sym_meta[2] if len(sym_meta) > 2 else "Unknown"

            for field in fields:
                sym_data[field] = sym.get(field, None)

            data.append(sym_data)

        return Response(
            {
                "count": len(data),
                "symbols": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": f"Failed to retrieve symbols: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    finally:
        if client is not None:
            client.shutdown()


# ----------------------------------------------------------------------------------------
# Calendar
# ----------------------------------------------------------------------------------------

CALENDAR_CSV_PATH = os.getenv(
    "CALENDAR_CSV_PATH",
    "/home/serveradmin/.mt5/drive_c/Program Files/MetaTrader 5/MQL5/Files/calendar_export.csv",
)


@api_view(["GET"])
def economic_calendar(request):
    """Reads the MT5 calendar export CSV and normalizes timestamps to UTC."""
    if not os.path.exists(CALENDAR_CSV_PATH):
        return Response(
            {"error": "Calendar data file not found. Ensure MQL5 service is running."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    imp_filter = request.query_params.get("importance", "2,3")
    curr_filter = request.query_params.get(
        "currency", "USD,EUR,GBP,JPY,AUD,CAD,CHF,NZD"
    )

    allowed_importance = (
        [i.strip() for i in imp_filter.split(",")] if imp_filter else []
    )
    allowed_currencies = (
        [c.strip().upper() for c in curr_filter.split(",")] if curr_filter else []
    )

    events = []
    LONG_MIN = "-9223372036854775808"

    try:
        with open(
            CALENDAR_CSV_PATH, "r", encoding="windows-1252", errors="replace"
        ) as f:
            reader = csv.DictReader(f)

            for row in reader:
                if allowed_importance and row["importance"] not in allowed_importance:
                    continue
                if allowed_currencies and row["currency"] not in allowed_currencies:
                    continue

                raw_time = int(row["time"])
                naive_dt = datetime.fromtimestamp(raw_time, tz=timezone.utc).replace(
                    tzinfo=None
                )
                broker_aware_dt = naive_dt.replace(tzinfo=BROKER_TZ)
                utc_dt = broker_aware_dt.astimezone(timezone.utc)

                def parse_val(val_str):
                    if val_str == LONG_MIN or not val_str:
                        return None
                    return float(val_str) / 1000000.0

                events.append(
                    {
                        "time": int(utc_dt.timestamp()),
                        "iso_time": utc_dt.isoformat(),
                        "event_id": row["event_id"],
                        "event_name": row["event_name"],
                        "currency": row["currency"],
                        "country": row.get("country", "N/A"),
                        "importance": int(row["importance"]),
                        "actual": parse_val(row["actual_value"]),
                        "forecast": parse_val(row["forecast_value"]),
                        "previous": parse_val(row["prev_value"]),
                    }
                )

        events.sort(key=lambda x: x["time"])

        return Response(
            {
                "count": len(events),
                "events": events,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": f"Failed to parse calendar data: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ----------------------------------------------------------------------------------------
# Trade Execution & Risk Management
# ----------------------------------------------------------------------------------------


@api_view(["GET"])
def open_positions(request):
    """Retrieve all currently open positions."""
    client = None
    try:
        client = MT5DataClient()
        symbol = request.query_params.get("symbol")  # Optional filter
        positions = client.get_open_positions(symbol=symbol)

        return Response(
            {
                "count": len(positions),
                "positions": positions,
                "timestamp": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        if client:
            client.shutdown()


@api_view(["POST"])
def execute_trade(request):
    """Execute a market BUY or SELL order."""
    client = None
    try:
        data = request.data
        symbol = data.get("symbol")
        volume = data.get("volume")
        order_type_str = data.get("type", "").upper()
        stop_loss = data.get("stop_loss", 0.0)
        take_profit = data.get("take_profit", 0.0)

        if not symbol or not volume or not order_type_str:
            return Response(
                {"error": "Missing required fields: 'symbol', 'volume', 'type'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if order_type_str == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
        elif order_type_str == "SELL":
            order_type = mt5.ORDER_TYPE_SELL
        else:
            return Response(
                {"error": "Invalid order type. Must be 'BUY' or 'SELL'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = MT5DataClient()
        result = client.execute_market_order(
            symbol=symbol,
            volume=float(volume),
            order_type=order_type,
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
        )

        return Response(
            {"status": "success", "ticket": result.get("order"), "details": result},
            status=status.HTTP_200_OK,
        )
    except RuntimeError as e:
        # MT5 specific trading errors (e.g., Not enough money)
        return Response({"error": str(e)}, status=status.HTTP_406_NOT_ACCEPTABLE)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        if client:
            client.shutdown()


@api_view(["POST"])
def flatten_positions(request):
    """Emergency Panic Button: Closes all open positions."""
    client = None
    try:
        client = MT5DataClient()
        results = client.flatten_all_positions()

        return Response(
            {"status": "executed", "summary": results}, status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        if client:
            client.shutdown()


@api_view(["GET"])
def trade_history(request):
    """Retrieve closed trades history and net PnL."""
    client = None
    try:
        days = int(request.query_params.get("days", 30))
        client = MT5DataClient()
        history = client.get_trade_history(days=days)

        # Calculate summary metrics
        total_profit = sum(d.get("profit", 0.0) for d in history)
        total_swap = sum(d.get("swap", 0.0) for d in history)
        total_commission = sum(d.get("commission", 0.0) for d in history)
        net_pnl = total_profit + total_swap + total_commission

        return Response(
            {
                "count": len(history),
                "net_pnl": net_pnl,
                "total_commission": total_commission,
                "deals": history,
                "timestamp": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:  # noqa: BLE001
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        if client:
            client.shutdown()


@api_view(["POST"])
def close_position(request):
    """Close a specific open position by its ticket ID."""
    client = None
    try:
        ticket = request.data.get("ticket")
        if not ticket:
            return Response(
                {"error": "Missing required field: 'ticket'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = MT5DataClient()
        result = client.close_position(int(ticket))

        return Response(
            {"status": "success", "details": result}, status=status.HTTP_200_OK
        )
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
    except RuntimeError as e:
        return Response({"error": str(e)}, status=status.HTTP_406_NOT_ACCEPTABLE)
    except Exception as e:  # noqa: BLE001
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        if client:
            client.shutdown()


@api_view(["GET"])
def market_movers(request):
    """Bulk endpoint to fetch daily D1 open/close for targeted symbols."""
    client = None
    try:
        # Read comma-separated symbols from query params if provided
        symbols_param = request.query_params.get("symbols")

        client = MT5DataClient()

        if symbols_param:
            target_symbols = [s.strip() for s in symbols_param.split(",") if s.strip()]
        else:
            all_syms = client.get_all_symbols()
            target_symbols = [s.get("name") for s in all_syms if s.get("name")]

        movers = []
        for sym_name in target_symbols:
            # Activate, query, and release
            mt5.symbol_select(sym_name, True)
            rates = mt5.copy_rates_from_pos(sym_name, mt5.TIMEFRAME_D1, 0, 1)

            if rates is not None and len(rates) > 0:
                candle = rates[0]
                movers.append(
                    {
                        "symbol": sym_name,
                        "open": float(candle["open"]),
                        "close": float(candle["close"]),
                    }
                )

        return Response(
            {"status": "success", "movers": movers}, status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        if client:
            client.shutdown()
