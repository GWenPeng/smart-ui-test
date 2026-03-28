"""Smart element locator with automatic iframe traversal."""
import asyncio
from playwright.async_api import Page, Frame, FrameLocator
from app.schemas.schemas import LogEntry


class IframeExplorer:
    """
    自动扫描页面所有 iframe，支持嵌套 iframe。
    在每个 frame context 中尝试定位目标元素。
    """

    @staticmethod
    async def scan_all_frames(page: Page, logs: list) -> list[dict]:
        """扫描页面所有 iframe 并返回层级结构"""
        frames_info = []

        async def _scan_frame(frame: Frame, depth: int, path: list[str]):
            info = {
                "name": frame.name or "",
                "url": frame.url,
                "depth": depth,
                "path": "/".join(path),
                "selector": None,
            }

            # Try to find iframe element in parent
            if frame != page.main_frame and frame.page == page:
                try:
                    parent = frame.parent_frame
                    if parent:
                        # Find the iframe element
                        iframe_el = await parent.query_selector(f'iframe[name="{frame.name}"]') if frame.name else None
                        if not iframe_el:
                            iframe_el = await parent.query_selector(f'iframe[src="{frame.url}"]') if frame.url else None
                        if not iframe_el:
                            # Fallback: find all iframes and match by order
                            all_iframes = await parent.query_selector_all("iframe")
                            for iframe in all_iframes:
                                src = await iframe.get_attribute("src") or ""
                                if src and src in frame.url:
                                    info["selector"] = f'iframe[src*="{src[:50]}"]'
                                    break
                            if not info["selector"] and all_iframes:
                                info["selector"] = "iframe"
                except Exception:
                    pass

            frames_info.append(info)
            child_frames = frame.child_frames
            for i, child in enumerate(child_frames):
                child_path = path + [f"frame[{i}]:{child.name or 'unnamed'}"]
                await _scan_frame(child, depth + 1, child_path)

        await _scan_frame(page.main_frame, 0, ["main"])

        logs.append(LogEntry(
            timestamp=_ts(),
            level="iframe",
            message=f"🔍 扫描完成，发现 {len(frames_info)} 个 frame",
            detail={"frames": frames_info},
        ))

        return frames_info

    @staticmethod
    async def find_element_in_frames(
        page: Page,
        locator_fn,
        timeout_per_frame: int = 3000,
        logs: list = None,
    ) -> tuple:
        """
        遍历所有 frame 尝试定位元素。
        返回 (element, frame, iframe_path) 或 (None, None, [])
        """
        if logs is None:
            logs = []

        visited = set()

        async def _try_frame(frame: Frame, path: list[str]):
            frame_id = id(frame)
            if frame_id in visited:
                return None, []
            visited.add(frame_id)

            # Try in this frame
            try:
                loc = locator_fn(frame)
                count = await loc.count()
                if count > 0:
                    logs.append(LogEntry(
                        timestamp=_ts(),
                        level="iframe",
                        message=f"🎯 在 iframe 中找到元素: {' > '.join(path)}",
                        detail={"path": path, "frame_url": frame.url},
                    ))
                    return frame, path
            except Exception:
                pass

            # Try child frames
            for i, child in enumerate(child_frames_safe(frame)):
                child_path = path + [f"iframe:{child.name or i}"]
                result_frame, result_path = await _try_frame(child, child_path)
                if result_frame:
                    return result_frame, result_path

            return None, []

        # Start from main frame
        result_frame, result_path = await _try_frame(page.main_frame, ["main"])
        return result_frame, result_path


def child_frames_safe(frame: Frame) -> list:
    """Safely get child frames."""
    try:
        return frame.child_frames
    except Exception:
        return []


def _ts():
    from datetime import datetime
    return datetime.utcnow().isoformat() + "Z"


# --- Locator strategies mapping ---
def build_locator(frame, strategy: str, value: str):
    """Build a Playwright locator from strategy + value."""
    strategy_map = {
        "role": lambda: frame.get_by_role(value),
        "text": lambda: frame.get_by_text(value, exact=False),
        "label": lambda: frame.get_by_label(value),
        "placeholder": lambda: frame.get_by_placeholder(value),
        "test_id": lambda: frame.get_by_test_id(value),
        "id": lambda: frame.locator(f"#{value}"),
        "name": lambda: frame.locator(f'[name="{value}"]'),
        "css": lambda: frame.locator(value),
        "xpath": lambda: frame.locator(f"xpath={value}"),
        "title": lambda: frame.get_by_title(value),
        "alt_text": lambda: frame.get_by_alt_text(value),
    }
    fn = strategy_map.get(strategy)
    if fn:
        return fn()
    # Fallback: try text
    return frame.get_by_text(value, exact=False)


async def smart_locate(
    page: Page,
    target: str,
    strategy: str = None,
    value: str = None,
    iframe_hint: str = None,
    timeout_ms: int = 10000,
    logs: list = None,
) -> tuple:
    """
    智能定位元素：
    1. 如果有明确的 strategy + value，先在主 frame 定位
    2. 如果找不到，自动遍历所有 iframe
    3. 支持 iframe_hint 缩小搜索范围
    """
    if logs is None:
        logs = []

    explorer = IframeExplorer()

    logs.append(LogEntry(
        timestamp=_ts(),
        level="locator",
        message=f"🔎 定位元素: \"{target}\"",
        detail={"strategy": strategy, "value": value, "iframe_hint": iframe_hint},
    ))

    if not strategy or not value:
        logs.append(LogEntry(
            timestamp=_ts(),
            level="warn",
            message="⚠️ 缺少定位策略，尝试智能推断...",
        ))
        # Try text-based fallback
        strategy = "text"
        value = target

    # 1. Try main frame first
    try:
        loc = build_locator(page.main_frame, strategy, value)
        count = await loc.count()
        if count > 0:
            logs.append(LogEntry(
                timestamp=_ts(),
                level="locator",
                message=f"✅ 在主页面找到元素 (count={count})",
                detail={"strategy": strategy, "value": value},
            ))
            return loc, page.main_frame, ["main"]
    except Exception as e:
        logs.append(LogEntry(
            timestamp=_ts(),
            level="debug",
            message=f"主页面未找到: {e}",
        ))

    # 2. Scan and search in iframes
    logs.append(LogEntry(
        timestamp=_ts(),
        level="iframe",
        message="🔄 主页面未找到，开始遍历 iframe...",
    ))

    frames_info = await explorer.scan_all_frames(page, logs)

    for frame_info in frames_info:
        if frame_info["depth"] == 0:
            continue  # skip main frame, already tried

        # If iframe_hint provided, filter frames
        if iframe_hint and iframe_hint.lower() not in (frame_info["url"] + frame_info["name"]).lower():
            continue

        try:
            frame = _get_frame_by_path(page, frame_info["path"])
            if frame:
                loc = build_locator(frame, strategy, value)
                count = await loc.count()
                if count > 0:
                    path_str = frame_info["path"]
                    logs.append(LogEntry(
                        timestamp=_ts(),
                        level="iframe",
                        message=f"✅ 在 iframe 中找到元素: {path_str}",
                        detail={"frame_url": frame_info["url"], "strategy": strategy},
                    ))
                    return loc, frame, path_str.split("/")
        except Exception:
            continue

    # 3. Deep traversal (async each frame)
    logs.append(LogEntry(
        timestamp=_ts(),
        level="locator",
        message="⚡ 执行深度遍历搜索...",
    ))

    result_frame, result_path = await explorer.find_element_in_frames(
        page,
        lambda f: build_locator(f, strategy, value),
        logs=logs,
    )

    if result_frame:
        loc = build_locator(result_frame, strategy, value)
        return loc, result_frame, result_path

    logs.append(LogEntry(
        timestamp=_ts(),
        level="error",
        message=f"❌ 未找到元素: \"{target}\"",
        detail={"strategy": strategy, "value": value},
    ))
    return None, None, []


def _get_frame_by_path(page: Page, path_str: str):
    """Get frame by path string."""
    parts = path_str.split("/")
    if not parts or parts[0] != "main":
        return None

    frame = page.main_frame
    for part in parts[1:]:
        if part.startswith("iframe:"):
            name = part[7:]
            try:
                idx = int(name)
                children = child_frames_safe(frame)
                if idx < len(children):
                    frame = children[idx]
                    continue
            except ValueError:
                pass
            # Try by name
            for child in child_frames_safe(frame):
                if child.name == name:
                    frame = child
                    break
    return frame
