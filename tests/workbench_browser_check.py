"""Opt-in local Chromium acceptance; all fixture data lives in a temporary workspace."""

import argparse
import csv
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import expect, sync_playwright
from finmy.workbench.store import Store


def check(chromium, output):
    output.mkdir(parents=True, exist_ok=True)
    errors, screenshots, assertions = [], [], []
    with tempfile.TemporaryDirectory(prefix="finmy-workbench-test-") as workspace:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        env = {**os.environ, "FINMY_WORKBENCH_HOME": workspace}
        with (output / "server.log").open("w") as log:
            process = subprocess.Popen([sys.executable, "-m", "finmy.workbench", "--port", str(port)],
                                       cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for _ in range(100):
                    try:
                        if opener.open(url + "/_stcore/health", timeout=1).status == 200:
                            break
                    except OSError:
                        time.sleep(.15)
                else:
                    raise RuntimeError("Local Streamlit health check failed")
                with sync_playwright() as p:
                    browser = p.chromium.launch(executable_path=chromium, headless=True, args=["--no-sandbox"])
                    context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
                    context.route("**/*", lambda route: route.continue_() if route.request.url.startswith((url, "data:", "blob:")) else route.abort())
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.set_default_timeout(20000)
                    page.goto(url)
                    expect(page.get_by_text("暂无事件", exact=True)).to_be_visible()
                    expect(page.get_by_role("heading", name="事件主表", exact=True)).to_be_visible()
                    expect(page.locator('[data-testid="stDataFrame"]:visible')).to_be_visible()
                    page.screenshot(path=str(output / "desktop-empty.png"), full_page=True)
                    screenshots.append("desktop-empty.png")
                    assertions.append("empty workspace")
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.wait_for_timeout(600)
                    expect(page.locator('[data-testid="stDataFrame"]:visible')).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
                    page.screenshot(path=str(output / "mobile-empty.png"), full_page=True)
                    screenshots.append("mobile-empty.png")
                    assertions.append("empty table visible on desktop and mobile")
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.wait_for_timeout(600)
                    page.get_by_text("新增事件", exact=True).click()
                    page.get_by_label("中文名称", exact=True).fill("港口复航测试事件")
                    page.get_by_label("英文名称", exact=True).fill("Port reopening test")
                    page.get_by_label("别名", exact=True).fill("港口恢复运营\nPort reopening")
                    page.get_by_label("事件简介", exact=True).fill("测试港口因天气关闭，随后完成复航。")
                    page.get_by_label("纳入范围", exact=True).fill("2025 年 1 月港口关闭及复航过程。")
                    page.get_by_role("button", name="保存事件").click()
                    expect(page.get_by_text("事件已保存", exact=True)).to_be_visible()
                    store = Store(workspace)
                    eid = store.events()[0]["event_id"]
                    assert store.event(eid)["aliases"] == ["港口恢复运营", "Port reopening"]
                    assertions.append("manual event creation")
                    page.locator('input[aria-label="审核人"]:visible').fill("验收人员")
                    page.get_by_role("button", name="保存范围确认").click()
                    expect(page.get_by_text("审核已保存", exact=True)).to_be_visible()
                    assert store.decision(eid, "scope") == "approved"
                    assertions.append("scope confirmation")
                    page.get_by_role("tab", name="资料与输入", exact=True).click()
                    upload = page.locator('[data-testid="stFileUploader"]').filter(has_text="TXT / 文本 PDF")
                    upload.locator('input[type="file"]').set_input_files({"name": "source.txt", "mimeType": "text/plain", "buffer": "2025年1月3日，港口恢复运营。".encode()})
                    page.wait_for_timeout(1000)
                    page.get_by_role("tab", name="资料与输入", exact=True).click()
                    page.get_by_role("button", name="保存资料").click()
                    expect(page.get_by_text("已保存 1 份资料", exact=True)).to_be_visible()
                    page.get_by_role("tab", name="资料与输入", exact=True).click()
                    page.locator('input[aria-label="审核人"]:visible').fill("验收人员")
                    page.get_by_role("button", name="保存审核").click()
                    expect(page.get_by_text("审核已保存", exact=True)).to_be_visible()
                    assert store.status(eid) == "待构建"
                    assertions.append("TXT upload and evidence approval")
                    graph = {"event_id": "synthetic-port", "title": {"value": "港口复航测试事件"}, "stages": [
                        {"stage_id": "S1", "name": {"value": "关闭与复航"}, "start_time": {"value": "2025-01-01"},
                         "end_time": {"value": "2025-01-04"}, "episodes": [
                            {"episode_id": "E1", "name": {"value": "恢复运营"}, "start_time": {"value": "2025-01-03"},
                             "end_time": {"value": "2025-01-03"}, "participants": [
                                {"participant_id": "P_1", "name": {"value": "港口管理方"}, "actions": [
                                    {"name": {"value": "恢复运营", "evidence_source_contents": ["2025年1月3日，港口恢复运营。"]}}]}],
                             "participant_relations": [], "transactions": []}]}]}
                    page.get_by_role("tab", name="图与修订", exact=True).click()
                    page.get_by_text("导入图", exact=True).click()
                    page.locator('[data-testid="stFileUploader"]').filter(has_text="FinalEventCascade JSON").locator('input[type="file"]').set_input_files(
                        {"name": "graph.json", "mimeType": "application/json", "buffer": json.dumps(graph, ensure_ascii=False).encode()})
                    page.wait_for_timeout(1000)
                    page.get_by_role("tab", name="图与修订", exact=True).click()
                    page.get_by_text("确认此图属于当前事件，并对应当前输入资料", exact=True).click()
                    page.get_by_role("button", name="保存原始图").click()
                    expect(page.get_by_text("原始图已保存", exact=True)).to_be_visible()
                    page.get_by_role("tab", name="图与修订", exact=True).click()
                    expect(page.locator(".js-plotly-plot")).to_be_visible()
                    assert page.locator(".barlayer path").count() >= 2
                    page.locator(".js-plotly-plot").scroll_into_view_if_needed()
                    page.screenshot(path=str(output / "desktop-graph.png"), full_page=True)
                    screenshots.append("desktop-graph.png")
                    assertions.append("explicit graph import and nonblank Gantt")
                    page.locator('input[aria-label="审核人"]:visible').fill("验收人员")
                    page.get_by_role("button", name="保存审核").click()
                    expect(page.get_by_text("审核已保存", exact=True)).to_be_visible()
                    assert store.status(eid) == "已收录"
                    assertions.append("graph approval")
                    # Reopen all four pages on desktop and mobile, including persisted data.
                    for size in ({"width": 1440, "height": 1000}, {"width": 390, "height": 844}):
                        page.set_viewport_size(size)
                        page.wait_for_timeout(600)
                        for name, title in (("任务", "任务"), ("待审", "待审"), ("设置", "设置"), ("数据", "事件数据")):
                            radio = page.locator('[data-testid="stSidebar"]').get_by_text(name, exact=True)
                            box = radio.bounding_box()
                            if not box or box["x"] < 0:
                                toggle = page.locator('[data-testid="stExpandSidebarButton"]')
                                toggle.click()
                                page.wait_for_timeout(400)
                            radio.click()
                            expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
                            page.wait_for_timeout(250)
                            if size["width"] < 600:
                                toggle = page.locator('[data-testid="stSidebarCollapseButton"] button')
                                if toggle.is_visible():
                                    toggle.click()
                                    page.wait_for_timeout(400)
                            assert page.locator('[data-testid="stException"]').count() == 0
                            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
                            filename = f"{size['width']}-{name}.png"
                            page.screenshot(path=str(output / filename), full_page=True)
                            screenshots.append(filename)
                            assertions.append(f"{size['width']} {name} layout")
                    page.get_by_role("tab", name="图与修订", exact=True).click()
                    expect(page.locator(".js-plotly-plot")).to_be_visible()
                    page.locator(".js-plotly-plot").scroll_into_view_if_needed()
                    page.screenshot(path=str(output / "mobile-graph.png"), full_page=True)
                    screenshots.append("mobile-graph.png")
                    page.reload()
                    expect(page.get_by_role("heading", name="事件数据", exact=True)).to_be_visible()
                    assert store.status(eid) == "已收录"
                    assertions.append("reload persistence")
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.wait_for_timeout(600)
                    page.get_by_text("导入主表", exact=True).click()
                    table = io.StringIO()
                    writer = csv.writer(table)
                    writer.writerow(["event_id", "old_name", "aliases", "scope_review"])
                    writer.writerow(["IMPORT-1", "Imported event", json.dumps(["Imported alias"]), "approved"])
                    page.locator('[data-testid="stFileUploader"]').filter(has_text="事件主表").locator('input[type="file"]').set_input_files(
                        {"name": "events.csv", "mimeType": "text/csv", "buffer": table.getvalue().encode()})
                    page.locator('[data-testid="stSelectbox"]').filter(has_text="old_name").locator('[role="combobox"]').click()
                    page.get_by_role("option", name="英文名称", exact=True).click()
                    expect(page.get_by_role("button", name="确认导入")).to_be_disabled()
                    page.get_by_text("确认不导入这些列：scope_review", exact=True).click()
                    page.get_by_role("button", name="确认导入").click()
                    expect(page.get_by_text("已导入 1 个事件", exact=True)).to_be_visible()
                    assert store.event("IMPORT-1")["aliases"] == ["Imported alias"]
                    assert store.decision("IMPORT-1", "scope") is None
                    assertions.append("explicit import mapping without inherited approval")
                    page.reload()
                    expect(page.get_by_role("heading", name="Imported event", exact=True)).to_be_visible()
                    grid = page.locator('[class*="st-key-master-"] .dvn-scroller').first
                    grid.evaluate("element => element.scrollIntoView({block: 'center'})")
                    page.wait_for_timeout(500)
                    grid.click(position={"x": 18, "y": 88})
                    expect(page.get_by_role("heading", name="港口复航测试事件", exact=True)).to_be_visible()
                    assertions.append("master row selection opens matching details")
                    page.screenshot(path=str(output / "desktop-master-selection.png"), full_page=True)
                    screenshots.append("desktop-master-selection.png")
                    assert not errors, errors
                    browser.close()
            except Exception:
                (output / "failure.json").write_text(json.dumps({"assertions": assertions, "errors": errors}, ensure_ascii=False))
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    report = {"assertions": assertions, "screenshots": screenshots, "page_errors": errors, "status": "pass"}
    (output / "acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(args.chromium, args.output)
