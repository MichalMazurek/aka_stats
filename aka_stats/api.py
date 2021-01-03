from typing import Any, Callable, Dict, List, Optional

from aka_stats.async_stats import NotFoundError, available_stats, contexts, fetch_stats, stat_history
from aka_stats.prometheus import prometheus_export
from aka_stats.stats import HISTORY_STAT_FIELDS, STAT_NAMES

try:
    from fastapi import FastAPI, Query, Body, HTTPException
    from starlette.responses import StreamingResponse
except ImportError:
    import warnings

    warnings.warn("FastAPI is not installed.")

    class FastAPI:
        def add_api_route(self, *args, **kwargs):
            pass

        pass

    class Query:
        def __init__(self, *args, **kwargs):
            pass

    Body = Query

    class StreamingResponse:
        pass


class FastApiPlaceHolder:
    def __init__(self):
        self.maps = []

    def get(self, path: str, *args, **kwargs):
        def decorator(func: Callable):
            self.maps.append(("get", func, path, args, kwargs))
            return func

        return decorator

    def post(self, path: str, *args, **kwargs):
        def decorator(func: Callable):
            self.maps.append(("post", func, path, args, kwargs))
            return func

        return decorator

    def attach_routes(self, app: FastAPI) -> FastAPI:
        """Attach stats routes to already existing FastAPI app.

        Current list of endpoints:
            - /api/v1/available-stats
            - /api/v1/stats/{label}
            - /api/v1/stats-history/{label}

        Args:
            app (FastAPI): app to attach routes too

        Returns:
            FastAPI: given app with attached routes
        """
        for map in self.maps:
            method, endpoint, path, args, kwargs = map
            app.add_api_route(path, endpoint, *args, methods=[method.upper()], **kwargs)

        return app


app = FastApiPlaceHolder()


@app.get("/api/v1/available-stats", response_model=List[str])
async def get_available_stats(matcher: str = Query("*", min_length=1)) -> List[str]:  # type: ignore
    """Get available stats in Redis."""
    return list({match async for match in available_stats(matcher)})


async def get_stats_dict(label: str) -> Dict[str, Optional[float]]:
    stats_data = await fetch_stats(label)
    return {stat_name: getattr(stats_data, stat_name) for stat_name in STAT_NAMES if stats_data is not None}


@app.get("/api/v1/stats/{label}", response_model=Dict[str, Optional[float]])
async def fetch_stats_data(label: str) -> Dict[str, Optional[float]]:
    """Get available stats in Redis."""
    try:
        return await get_stats_dict(label)
    except NotFoundError:
        raise HTTPException(404)


@app.post("/api/v1/stats", response_model=Dict[str, Dict[str, Optional[float]]])
async def fetch_batch_stats_data(labels: List[str] = Body(...)) -> Dict[str, Dict[str, Optional[float]]]:  # type: ignore
    """Get available stats in Redis."""

    async def ignore_missing(label: str) -> Dict[str, Optional[float]]:
        try:
            return await get_stats_dict(label)
        except NotFoundError:
            return {}

    return {label: await ignore_missing(label) for label in labels}


@app.get("/api/v1/stats-history/{label}", response_model=List[Dict[str, Any]])
async def fetch_stats_history(label: str) -> List[Dict[str, Any]]:
    """Get available stats in Redis."""
    return [{k: getattr(stat, k) for k in HISTORY_STAT_FIELDS} for stat in await stat_history(label)]


@app.post("/api/v1/stat-contexts", response_model=Dict[str, str])
async def fetch_stat_contexts(context_ids: List[str] = Body(...)) -> Dict[str, str]:  # type: ignore
    """Get batch of context ids."""
    if not context_ids:
        return {}
    return {key: value.decode("utf8") for key, value in (await contexts(context_ids)).items()}


@app.get("/api/v1/stats-prometheus", response_model=str)
async def export_to_prometheus(matcher: str = Query("*")) -> StreamingResponse:
    """Export data to prometheus."""
    return StreamingResponse(prometheus_export(matcher), media_type="plain/text")
