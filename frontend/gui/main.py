import json
import os
from typing import Any
from urllib.parse import unquote

import httpx
import streamlit as st


API_BASE = os.getenv(
    "BACKEND_BASE_URL", "http://127.0.0.1:8000/api/v1"
).rstrip("/")
TIMEOUT = httpx.Timeout(60.0, connect=10.0)
AUTH_COOKIE_ACCESS = "kb_rag_at"
AUTH_COOKIE_REFRESH = "kb_rag_rt"
AUTH_COOKIE_MAX_AGE = 60 * 60 * 24 * 7

st.set_page_config(page_title="KB RAG Agent", page_icon="📚", layout="wide")
st.title("📚 KB RAG Agent")

_AUTH_COOKIE_BRIDGE = st.components.v2.component(
    "kb_rag_auth_cookies",
    html="<span aria-hidden='true'></span>",
    js="""
export default function (component) {
  const { data } = component
  if (!data) return
  const base = "; Path=/; SameSite=Lax"
  if (data.clear) {
    document.cookie = "kb_rag_at=" + base + "; Max-Age=0"
    document.cookie = "kb_rag_rt=" + base + "; Max-Age=0"
    return
  }
  if (data.access_token) {
    const maxAge = "; Max-Age=" + String(data.max_age || 604800)
    document.cookie =
      "kb_rag_at=" + encodeURIComponent(data.access_token) + base + maxAge
    document.cookie =
      "kb_rag_rt=" +
      encodeURIComponent(data.refresh_token || "") +
      base +
      maxAge
  }
}
""",
)


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {st.session_state.access_token}"}


def api_error(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
        return str(detail or response.text)
    except (ValueError, AttributeError):
        return response.text or f"HTTP {response.status_code}"


def read_auth_cookie(name: str) -> str | None:
    raw = st.context.cookies.get(name)
    if not raw:
        return None
    return unquote(raw)


def try_refresh_access(refresh_token: str) -> str | None:
    try:
        response = httpx.request(
            "GET",
            f"{API_BASE}/auth/refresh-token",
            headers={"Authorization": f"Bearer {refresh_token}"},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError:
        return None
    if not response.is_success:
        return None
    return response.json().get("access_token")


def restore_auth_from_cookies() -> None:
    if st.session_state.get("access_token"):
        return
    if st.session_state.get("_skip_cookie_restore"):
        return

    access = read_auth_cookie(AUTH_COOKIE_ACCESS)
    refresh = read_auth_cookie(AUTH_COOKIE_REFRESH)
    if not access and not refresh:
        return

    # Access tokens expire quickly; always prefer refresh when available.
    if refresh:
        new_access = try_refresh_access(refresh)
        if new_access:
            st.session_state.access_token = new_access
            st.session_state.refresh_token = refresh
            return
        st.session_state["_skip_cookie_restore"] = True
        st.session_state["_clear_auth_cookies"] = True
        return

    st.session_state.access_token = access


def persist_auth_cookies() -> None:
    if not st.session_state.get("access_token"):
        return
    _AUTH_COOKIE_BRIDGE(
        key="auth_cookie_bridge",
        data={
            "access_token": st.session_state.access_token,
            "refresh_token": st.session_state.get("refresh_token", ""),
            "max_age": AUTH_COOKIE_MAX_AGE,
            "clear": False,
        },
        height=0,
    )


def clear_auth_cookies() -> None:
    _AUTH_COOKIE_BRIDGE(
        key="auth_cookie_bridge",
        data={"clear": True},
        height=0,
    )


def reset_login() -> None:
    for key in (
        "access_token",
        "refresh_token",
        "knowledge_base_id",
        "thread_id",
        "messages",
        "thread_edit_id",
        "pending_delete_thread_id",
        "pending_delete_kb_id",
        "upload_notice",
    ):
        st.session_state.pop(key, None)
    st.session_state["_clear_auth_cookies"] = True
    st.session_state["_skip_cookie_restore"] = True


def accept_login_tokens(access_token: str, refresh_token: str) -> None:
    st.session_state.access_token = access_token
    st.session_state.refresh_token = refresh_token
    st.session_state.pop("_skip_cookie_restore", None)
    st.session_state.pop("_clear_auth_cookies", None)
    st.session_state.pop("_refresh_attempted", None)


def request(
    method: str,
    path: str,
    *,
    authenticated: bool = True,
    **kwargs: Any,
) -> httpx.Response:
    headers = kwargs.pop("headers", {})
    if authenticated:
        headers = {**headers, **auth_headers()}
    response = httpx.request(
        method,
        f"{API_BASE}{path}",
        headers=headers,
        timeout=TIMEOUT,
        **kwargs,
    )
    if response.status_code == 401 and authenticated:
        refresh = st.session_state.get("refresh_token") or read_auth_cookie(
            AUTH_COOKIE_REFRESH
        )
        if refresh and not st.session_state.get("_refresh_attempted"):
            st.session_state["_refresh_attempted"] = True
            new_access = try_refresh_access(refresh)
            if new_access:
                st.session_state.access_token = new_access
                st.session_state.refresh_token = refresh
                retry_headers = {**headers, **auth_headers()}
                retry = httpx.request(
                    method,
                    f"{API_BASE}{path}",
                    headers=retry_headers,
                    timeout=TIMEOUT,
                    **kwargs,
                )
                if retry.status_code != 401:
                    st.session_state.pop("_refresh_attempted", None)
                    return retry
        reset_login()
        st.error("登录已失效，请重新登录。")
        st.rerun()
    return response


def show_auth() -> None:
    # Keep clearing stale cookies while login is shown (JS clear is async).
    if st.session_state.get("_skip_cookie_restore"):
        clear_auth_cookies()

    login_tab, signup_tab = st.tabs(["登录", "注册"])
    with login_tab:
        with st.form("login_form"):
            email = st.text_input("邮箱", key="login_email")
            password = st.text_input("密码", type="password", key="login_password")
            submitted = st.form_submit_button("登录", use_container_width=True)
        if submitted:
            try:
                response = request(
                    "POST",
                    "/auth/login",
                    authenticated=False,
                    json={"email": email, "password": password},
                )
                if response.is_success:
                    tokens = response.json()
                    accept_login_tokens(
                        tokens["access_token"], tokens["refresh_token"]
                    )
                    st.rerun()
                st.error(api_error(response))
            except httpx.ConnectError as exc:
                st.error(
                    "无法连接后端（127.0.0.1:8000）。请先启动 PostgreSQL，"
                    "再在 backend 目录运行 `python run_dev.py`。"
                    f" 详情：{exc}"
                )
            except httpx.HTTPError as exc:
                st.error(f"无法连接后端：{exc}")

    with signup_tab:
        with st.form("signup_form"):
            email = st.text_input("邮箱", key="signup_email")
            password = st.text_input(
                "密码（至少 8 位）", type="password", key="signup_password"
            )
            submitted = st.form_submit_button("注册", use_container_width=True)
        if submitted:
            try:
                response = request(
                    "POST",
                    "/auth/signup",
                    authenticated=False,
                    json={"email": email, "password": password},
                )
                if response.is_success:
                    st.success("注册成功，请切换到登录页。")
                else:
                    st.error(api_error(response))
            except httpx.ConnectError as exc:
                st.error(
                    "无法连接后端（127.0.0.1:8000）。请先启动 PostgreSQL，"
                    "再在 backend 目录运行 `python run_dev.py`。"
                    f" 详情：{exc}"
                )
            except httpx.HTTPError as exc:
                st.error(f"无法连接后端：{exc}")


def load_history(thread_id: str) -> None:
    response = request("GET", f"/chat/{thread_id}")
    if response.is_success:
        st.session_state.messages = [
            item
            for item in response.json()["messages"]
            if item["role"] in {"user", "assistant"}
        ]
    else:
        st.session_state.messages = []
        st.error(api_error(response))


def select_thread(thread_id: str) -> None:
    if st.session_state.get("thread_id") != thread_id:
        st.session_state.thread_id = thread_id
        st.session_state.pop("thread_edit_id", None)
        st.session_state.pop("pending_delete_thread_id", None)
        load_history(thread_id)


def rename_thread(thread_id: str, title: str) -> bool:
    response = request("PATCH", f"/threads/{thread_id}", json={"title": title})
    if response.is_success:
        return True
    st.error(api_error(response))
    return False


def delete_thread(thread_id: str) -> None:
    response = request("DELETE", f"/threads/{thread_id}")
    if not response.is_success and response.status_code != 204:
        st.error(api_error(response))
        return
    st.session_state.pop("thread_edit_id", None)
    st.session_state.pop("pending_delete_thread_id", None)
    if st.session_state.get("thread_id") == thread_id:
        st.session_state.pop("thread_id", None)
        st.session_state.pop("messages", None)
    st.rerun()


def create_session(kb_id: str, title: str) -> None:
    response = request(
        "POST",
        "/threads/",
        json={"title": title, "knowledge_base_id": kb_id},
    )
    if response.is_success:
        select_thread(response.json()["id"])
        st.session_state.pop("thread_edit_id", None)
        st.rerun()
    st.error(api_error(response))


def fetch_documents(kb_id: str) -> list[dict[str, Any]]:
    response = request("GET", f"/documents/{kb_id}")
    if not response.is_success:
        st.error(api_error(response))
        return []
    return response.json()


def show_kb_list() -> None:
    response = request("GET", "/knowledge-bases/")
    if not response.is_success:
        st.error(api_error(response))
        return
    knowledge_bases = response.json()
    for kb in knowledge_bases:
        if st.button(
            kb["name"],
            key=f"kb-{kb['id']}",
            width="stretch",
            type=(
                "primary"
                if kb["id"] == st.session_state.get("knowledge_base_id")
                else "secondary"
            ),
        ):
            st.session_state.knowledge_base_id = kb["id"]
            st.session_state.pop("thread_id", None)
            st.session_state.pop("messages", None)
            st.session_state.pop("thread_edit_id", None)
            st.rerun()

    with st.expander("新建知识库", expanded=not knowledge_bases):
        with st.form("new_kb_form"):
            name = st.text_input("名称", value="新知识库")
            description = st.text_input("描述（可选）", value="")
            create = st.form_submit_button("创建", width="stretch")
        if create:
            create_response = request(
                "POST",
                "/knowledge-bases/",
                json={"name": name, "description": description},
            )
            if create_response.is_success:
                st.session_state.knowledge_base_id = create_response.json()["id"]
                st.session_state.pop("thread_id", None)
                st.session_state.pop("messages", None)
                st.session_state.pop("thread_edit_id", None)
                st.rerun()
            st.error(api_error(create_response))


def show_kb_workspace(kb_id: str) -> None:
    kb_response = request("GET", f"/knowledge-bases/{kb_id}")
    if not kb_response.is_success:
        st.session_state.pop("knowledge_base_id", None)
        st.error(api_error(kb_response))
        return
    kb = kb_response.json()

    if st.button("← 全部知识库", use_container_width=True):
        st.session_state.pop("knowledge_base_id", None)
        st.session_state.pop("thread_id", None)
        st.session_state.pop("messages", None)
        st.session_state.pop("thread_edit_id", None)
        st.rerun()

    st.subheader(kb["name"])
    if kb.get("description"):
        st.caption(kb["description"])

    pending_kb = st.session_state.get("pending_delete_kb_id")
    if pending_kb == kb_id:
        st.warning("确认删除该知识库？文档与下属会话都会删除。")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("确认删除知识库", type="primary", use_container_width=True):
                response = request("DELETE", f"/knowledge-bases/{kb_id}")
                if response.is_success or response.status_code == 204:
                    for key in (
                        "knowledge_base_id",
                        "thread_id",
                        "messages",
                        "pending_delete_kb_id",
                        "thread_edit_id",
                    ):
                        st.session_state.pop(key, None)
                    st.rerun()
                st.error(api_error(response))
        with c2:
            if st.button("取消删除知识库", use_container_width=True):
                st.session_state.pop("pending_delete_kb_id", None)
                st.rerun()
    elif st.button("删除知识库", use_container_width=True):
        st.session_state.pending_delete_kb_id = kb_id
        st.rerun()

    with st.expander("上传文档", expanded=False):
        uploaded_file = st.file_uploader(
            "PDF / DOCX / TXT",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=False,
            key=f"uploader-{kb_id}",
        )
        if st.button(
            "上传到知识库",
            disabled=uploaded_file is None,
            use_container_width=True,
        ):
            response = request(
                "POST",
                f"/documents/upload/{kb_id}",
                files={
                    "file": (
                        uploaded_file.name,
                        uploaded_file.getvalue(),
                        uploaded_file.type,
                    )
                },
            )
            if response.is_success:
                st.session_state.upload_notice = (
                    f"已上传到知识库：{response.json()['file_name']}"
                )
                st.rerun()
            st.error(api_error(response))

    st.divider()
    threads_response = request("GET", f"/threads/?knowledge_base_id={kb_id}")
    if not threads_response.is_success:
        st.error(api_error(threads_response))
        return
    threads = threads_response.json()

    st.markdown("**会话**")
    for thread in threads:
        select_col, edit_col = st.columns([5, 1])
        button_type = (
            "primary"
            if thread["id"] == st.session_state.get("thread_id")
            else "secondary"
        )
        with select_col:
            if st.button(
                thread["title"],
                key=f"thread-{thread['id']}",
                type=button_type,
                use_container_width=True,
            ):
                select_thread(thread["id"])
                st.rerun()
        with edit_col:
            if st.button(
                "⋯",
                key=f"thread-edit-{thread['id']}",
                use_container_width=True,
                help="在主区重命名 / 删除",
            ):
                if st.session_state.get("thread_edit_id") == thread["id"]:
                    st.session_state.pop("thread_edit_id", None)
                    st.session_state.pop("pending_delete_thread_id", None)
                else:
                    st.session_state.thread_edit_id = thread["id"]
                    st.session_state.pop("pending_delete_thread_id", None)
                st.rerun()


def show_sidebar() -> None:
    with st.sidebar:
        st.header("知识库")

        kb_id = st.session_state.get("knowledge_base_id")
        if kb_id:
            show_kb_workspace(kb_id)
        else:
            show_kb_list()

        st.divider()
        if st.button(
            "退出登录",
            type="tertiary",
            icon=":material/logout:",
            width="content",
        ):
            reset_login()
            st.rerun()


def show_pinned_documents(kb_id: str) -> None:
    docs = fetch_documents(kb_id)
    notice = st.session_state.pop("upload_notice", None)
    if notice:
        st.success(notice)
        st.toast(notice)

    left, right = st.columns([3, 1])
    with left:
        st.markdown("**知识库文档**（点击可新建会话）")
    with right:
        if st.button("新建空白会话", use_container_width=True):
            create_session(kb_id, "新会话")

    if not docs:
        st.caption("还没有文档。请在左侧「上传文档」加入知识库。")
        return

    for start in range(0, len(docs), 4):
        row = docs[start : start + 4]
        cols = st.columns(4)
        for col, doc in zip(cols, row):
            with col:
                label = doc["file_name"]
                if len(label) > 22:
                    label = label[:19] + "…"
                if st.button(
                    label,
                    key=f"pin-doc-{doc['id']}",
                    use_container_width=True,
                    help=f"以「{doc['file_name']}」新建会话",
                ):
                    create_session(kb_id, doc["file_name"])


def show_thread_edit_panel(kb_id: str) -> None:
    """Session rename/delete lives on the main canvas, not the crowded sidebar."""
    edit_id = st.session_state.get("thread_edit_id")
    if not edit_id:
        return
    response = request("GET", f"/threads/?knowledge_base_id={kb_id}")
    if not response.is_success:
        return
    thread = next((item for item in response.json() if item["id"] == edit_id), None)
    if thread is None:
        st.session_state.pop("thread_edit_id", None)
        return

    with st.container(border=True):
        st.markdown(f"**编辑会话：{thread['title']}**")
        with st.form(f"edit_thread_{thread['id']}"):
            new_title = st.text_input("名称", value=thread["title"])
            save = st.form_submit_button("保存名称")
        if save:
            title = new_title.strip()
            if not title:
                st.error("名称不能为空")
            elif rename_thread(thread["id"], title):
                st.session_state.pop("thread_edit_id", None)
                st.rerun()

        pending = st.session_state.get("pending_delete_thread_id")
        b1, b2, b3 = st.columns(3)
        with b1:
            if pending == thread["id"]:
                if st.button("确认删除", type="primary", use_container_width=True):
                    delete_thread(thread["id"])
            elif st.button("删除会话", use_container_width=True):
                st.session_state.pending_delete_thread_id = thread["id"]
                st.rerun()
        with b2:
            if pending == thread["id"]:
                if st.button("取消删除", use_container_width=True):
                    st.session_state.pop("pending_delete_thread_id", None)
                    st.rerun()
        with b3:
            if st.button("收起", use_container_width=True):
                st.session_state.pop("thread_edit_id", None)
                st.session_state.pop("pending_delete_thread_id", None)
                st.rerun()


def stream_answer(thread_id: str, prompt: str) -> str:
    answer = ""
    answer_box = st.empty()
    tool_lines: list[str] = []
    with st.expander("工具调用", expanded=False):
        tool_box = st.empty()
    try:
        with httpx.stream(
            "POST",
            f"{API_BASE}/chat/{thread_id}",
            headers=auth_headers(),
            json={"message": prompt},
            timeout=TIMEOUT,
        ) as response:
            if not response.is_success:
                response.read()
                st.error(api_error(response))
                return ""
            for line in response.iter_lines():
                if not line:
                    continue
                event = json.loads(line)
                event_type = event.get("type")
                if event_type == "llm_chunk":
                    answer += str(event.get("content", ""))
                    answer_box.markdown(answer + "▌")
                elif event_type == "tool_call":
                    tool_lines.append(f"调用 `{event.get('name', 'unknown')}`")
                    tool_box.markdown("\n\n".join(tool_lines))
                elif event_type == "tool_result":
                    tool_lines.append(f"`{event.get('name', 'unknown')}` 已返回结果")
                    tool_box.markdown("\n\n".join(tool_lines))
                elif event_type == "error":
                    st.error(str(event.get("content", "未知错误")))
        answer_box.markdown(answer)
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        st.error(f"对话流中断：{exc}")
    return answer


if st.session_state.pop("_clear_auth_cookies", False):
    clear_auth_cookies()
    st.session_state["_skip_cookie_restore"] = True
elif not st.session_state.get("_skip_cookie_restore"):
    restore_auth_from_cookies()
    # restore may schedule a cookie clear when refresh fails
    if st.session_state.pop("_clear_auth_cookies", False):
        clear_auth_cookies()
        st.session_state["_skip_cookie_restore"] = True

if "access_token" not in st.session_state:
    show_auth()
    st.stop()

persist_auth_cookies()
show_sidebar()
kb_id = st.session_state.get("knowledge_base_id")
thread_id = st.session_state.get("thread_id")
if not kb_id:
    st.info("请先在左侧选择知识库；没有时可展开「新建知识库」。")
    st.stop()

show_pinned_documents(kb_id)
show_thread_edit_panel(kb_id)
st.divider()

if not thread_id:
    st.info("点击上方文档可新建会话，或点「新建空白会话」。同一知识库无需重复上传。")
    st.stop()

for message in st.session_state.get("messages", []):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("向当前知识库提问"):
    st.session_state.setdefault("messages", []).append(
        {"role": "user", "content": prompt}
    )
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        answer = stream_answer(thread_id, prompt)
    if answer:
        st.session_state.messages.append(
            {"role": "assistant", "content": answer}
        )
