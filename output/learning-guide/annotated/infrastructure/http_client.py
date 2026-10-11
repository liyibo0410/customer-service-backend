# 【导读】infrastructure/http_client.py ｜ 基础设施层：封装对"电商中台"的 HTTP 访问客户端
# 【导读】被谁调用：需要订单/商品等中台数据的上层（Service/Engine）复用这个全局单例
# 【导读】要点：AsyncClient 复用连接池，避免每个请求都重新握手建连

# itwwy/infrastructure/http_client.py

# 教:导入 asyncio，为底部 __main__ 自测提供事件循环运行器
import asyncio
# 教:httpx 是支持 async/await 的 HTTP 库；AsyncClient 是其异步客户端
from httpx import AsyncClient
# 全局变量
# 教:全局单例客户端，先占位 None；等服务启动时再真正创建
http_client: AsyncClient | None = None
#初始化
# 教:初始化函数：创建可复用的连接对象（原注释：相当于"打开一个浏览器"）
def init_http_client():
    # 教:global 声明：要改的是模块级变量，而不是新建局部同名变量
    global http_client
    # 教:AsyncClient 内部自动复用连接；timeout=10 防止某个请求无限挂起
    http_client = AsyncClient(timeout=10.0)   # 初始化了一个 请求对象 打开浏览器
# 关闭
# 教:关闭也做成协程，因为 aclose 内部需要等待资源真正释放
async def close_http_client():
    # 教:先判断非空再关闭，避免对 None 操作或重复关闭报错
    if http_client is not None:         # 不为none 关闭之前 先 判断 是不是真的有这个客户端
        # 教:aclose 释放底层连接池，服务退出前调用
        await http_client.aclose()

# 异步  请求一个 特别慢 （后台慢慢进行） 下一个任务

# 教:直接运行本文件即自测；被 import 时这段不执行
if __name__ == '__main__':
    # 教:测试函数定义为协程，方便统一交给 asyncio.run 驱动
    async def test():
        # 教:先初始化客户端，模拟真实项目"启动先初始化"的流程
        init_http_client()
        # 教:await 发 GET 等响应（原注释：阻塞）；期间可切去处理其他任务
        result = await http_client.get('http://localhost:18081/users/u1001/orders')    # 阻塞
        # 教:响应转成 JSON，逐层取 data.orders 列表并打印订单数据
        print(result.json()['data']['orders'])

        # 教:自测结束关闭客户端，释放连接资源
        await close_http_client()


    # 教:asyncio.run 负责创建并回收事件循环，运行协程 test()
    asyncio.run(test())
