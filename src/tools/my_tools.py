import os
import tempfile
import uuid
from datetime import datetime

from langchain_core.tools import tool
from zai import ZhipuAiClient

from common.env_utils import ZHIPU_API_KEY, QINIU_ACCESS_KEY, QINIU_SECRET_KEY, QINIU_BUCKET_NAME, QINIU_BUCKET_DOMAIN

client = ZhipuAiClient(api_key=ZHIPU_API_KEY)

@tool('web_search', parse_docstring=True)
def web_search(query: str) -> str:
    """
    使用搜狗的API进行Web搜索

    Args:
        query: 需要搜索的内容或者关键字。

    Returns:
        返回搜索之后的结果
    """
    try:
        response = client.web_search.web_search(
            search_engine="search_std",
            search_query=query,
            count=3,  # 返回结果的条数，范围1-50，默认10
            search_recency_filter="noLimit",  # 搜索指定日期范围内的内容
        )
        if response.search_result:
            return "\n\n".join([d.content for d in response.search_result])
        return '没有搜索到任何内容！'
    except Exception as e:
        print(e)
        return f"搜索失败: {e}"


@tool('upload_to_qiniu', parse_docstring=True)
def upload_to_qiniu(local_path: str) -> str:
    """
    上传本地文件到七牛云对象存储，返回可访问的URL地址。
    文件名自动生成，格式为 uploads/{年}/{月}/{日}/{uuid}.{扩展名}。
    支持宿主机本地路径和沙箱内路径（自动从沙箱下载后上传）。

    Args:
        local_path: 要上传的文件路径。支持宿主机本地路径和沙箱内绝对路径（如 /temp/test.html）。

    Returns:
        上传成功后返回文件的完整访问URL，失败则返回错误信息。
    """
    if not all([QINIU_ACCESS_KEY, QINIU_SECRET_KEY, QINIU_BUCKET_NAME, QINIU_BUCKET_DOMAIN]):
        return "错误：七牛云配置不完整，请检查 .env 中的 QINIU_ACCESS_KEY、QINIU_SECRET_KEY、QINIU_BUCKET_NAME、QINIU_BUCKET_DOMAIN"

    # 延迟导入避免循环依赖
    from agent.agent_state import sandbox_backend

    if sandbox_backend is None:
        return "错误：沙箱未连接，无法读取文件"

    # 从沙箱下载文件
    temp_file = None
    try:
        responses = sandbox_backend.download_files([local_path])
        resp = responses[0]
        if resp.error or resp.content is None:
            return f"错误：沙箱中未找到文件 — {local_path}（{resp.error}）"

        # 写入临时文件供上传
        ext = os.path.splitext(local_path)[1]
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp_file.write(resp.content)
        temp_file.close()

        from qiniu import Auth, put_file_v2

        q = Auth(QINIU_ACCESS_KEY, QINIU_SECRET_KEY)

        # 自动生成 key：uploads/YYYY/MM/DD/uuid.ext
        today = datetime.now().strftime("%Y/%m/%d")
        key = f"uploads/{today}/{uuid.uuid4().hex}{ext}"

        token = q.upload_token(QINIU_BUCKET_NAME, key, 3600)
        ret, info = put_file_v2(token, key, temp_file.name, version='v2')

        if ret and ret.get('key') == key:
            base_url = f"https://{QINIU_BUCKET_DOMAIN}/{key}"
            # 私有空间需要生成带签名的下载链接，有效期 3600 秒
            signed_url = q.private_download_url(base_url, expires=3600)
            return signed_url
        else:
            return f"上传失败：{info}"
    except ImportError:
        return "错误：未安装 qiniu SDK，请执行 pip install qiniu"
    except Exception as e:
        return f"上传异常：{e}"
    finally:
        if temp_file and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
