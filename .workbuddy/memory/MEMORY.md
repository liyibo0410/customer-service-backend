# 项目长期记忆（customer-service-backend）

## 项目定位
- 本仓库是学习型复刻项目：把教程「电商小二」代码（原包名 `itwwy`）按 day01~dayNN 逐节落地到本仓库（包名去掉 `itwwy.` 前缀，直接用 `domain/` `task/` `engine/` 等顶层包）。教程资料在 `D:\个人文件\AI大模型学习资料\16-智能客服\day07\`。
- 装配入口：`engine/builder.py` 的 `build_dialogue_engine()` 单例；API 在 `api/routers/dependencies.py` 复用该 builder（勿再照抄课程 3.3 的手写装配，那版跑不起来）。

## 运行环境 / 端口分布（排查「请求失败」先看这个）
- 前端 Vite dev：`external/customer-service-frontend`，端口 **5173**（`vite.config.js` 里 proxy 把 `/api`→18082、`/commerce`→18081）。
- AI 客服后端：本仓库 `main.py`，端口 **18082**（`APP_PORT`）。
  - 便利路由：`GET /` 回服务说明 + 接口清单、`GET /health` 回 `{"status":"ok"}`（`vite.config.js` 里那条 `/health` 代理的落点）。以前直接开 `http://127.0.0.1:18082` 是 404，属正常但易误判成「后端挂了」。
- 商城中台：**18081**（`COMMERCE_API_BASE_URL`），工程在**本仓库内** ——
  `external/ecommerce-service-backend`（自带 `.venv`，可直接 `./.venv/Scripts/python.exe main.py`）。
  ⚠️ 别再去课程资料目录找它：`external/` 就是教程原工作区，`external/{customer-service-frontend,ecommerce-service-backend,docker,documnents}` 都在这里，与课程资料里那份逐字节相同。
- MySQL：**`127.0.0.1:3307`**（2026-10-07 起，见下），库 `customer_service`。
- LLM：阿里云 MaaS `qwen3.7-plus`，端点 `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`。
- **一键启动**：`start-dev.bat` 或 `uv run python tools/dev_up.py`（会自动拉起 MySQL 容器 + 中台 + 后端 + 前端）；`--status` 只看状态、`--stop` 停后端与前端、`--init-db` 建库建表。
- **⚠️ MySQL 为什么是 3307**：本机 Docker Desktop 上另一个项目 `ecommerce-operation-assistant`
  的 `mysql:8.4` 容器长期占着 `127.0.0.1:3306` 且其 root 口令已丢失，谁去连都是
  `1045 Access denied for user 'root'@'172.22.0.1'`（`172.22.0.1` 这一个来源 IP 就说明
  「3306 后面是 Docker 容器」，不是本机原生 MySQL）。课程的 MySQL 因此改发布到宿主 **3307**。
- **我们的 MySQL 容器与数据卷**（口令与课程 `docker/docker-compose.yml` 一致，`root:itwwy123@`）：
  - **唯一定义处**：`external/docker/docker-compose.yml`（容器 `customer-service-mysql`、`mysql:8.4`、
    `-p 127.0.0.1:3307:3306`、`--restart unless-stopped`）。起库一律
    `docker compose -f external/docker/docker-compose.yml up -d`，**别再手抄 `docker run` 参数**。
  - 卷 **`docker_mysql_data`** —— 数据全在这（`customer_service.dialogue_states` + `commerce` 的
    users/orders/products/refunds/logistics）。**容器可以随便删（compose 能重建），卷千万别删。**
  - 卷不在时靠 `external/docker/mysql/initdb/*.sql` 重建（001 建 customer_service、002 建 commerce）。
- **常见坑**：
  - 前端红条三件套 = 后端/中台/MySQL 三缺一：`加载历史消息失败。`→18082 或 MySQL；
    `加载订单列表失败。`→18081 中台；`请求失败，请重新尝试`→18082 没起。
  - `mysqladmin ping` **认证失败也返回 exit 0**，compose 的 healthcheck 是假阳性 ——
    别信它显示 `healthy`，要用 `mysql -uroot -p... -e "select 1"` 验证。
  - 从工具沙箱 spawn 的服务会在工具调用结束时被回收，长期运行必须让用户自己跑 `start-dev.bat`。

## 文档自身笔误清单（照抄必翻车，已踩坑）
- day07 文档 4.3：`state.start_system_task(...)` → 实际方法名是 `start_active_system_task`。
- day07 文档 7.1：`state.resume_task(...)` → 实际方法名是 `resumed_active_task(flow_id=None)`（返回 bool）。
- day07 文档 6.1：`_handle_cancel_flow` 未防御「无活跃任务」，照抄会 AttributeError。
- day07 文档 3.3：装配代码缺 import、文件名 `user_flows.yml` 少了 s、DialogueEngine 参数对不上。
- 粘贴代码块时若含 `StartedSystemContext` 调用，必须确认 `_activate_started_system_flow` 已定义且已 import（历史上缺失过）。
- day11 历史接口：`HistoryBuilder` 两个方法名是 `render_user_message` + `render_bot_messages`（**bot 是复数**）。`output/build_guide.py` 写成了单数 `render_bot_message`，照抄会导致 `load_chat_history` 调用不存在的属性 → `/api/chat/history` 500。

## 约定
- `resumed_active_task(flow_id=None)`：None=恢复暂停栈栈顶（用户说"继续刚才的"）。
- 任务生命周期：打断=挂起进 paused_tasks（可恢复），取消=丢弃（Canceled 过场）。
- 每轮先 CommandProcessor 改状态（激活过场 SystemContext），再由 FlowExecutor 消费过场推进业务流。
- `DialogueState.active_system_task` 字段类型必须是 `SystemContextUnion`（contexts.py 的判别联合），不能用父类 `SystemContext`——父类 model_validate 会吞掉 Started/Collected 等子类字段，多轮持久化必丢数据。
- LLM 的 available_flows 只给业务流程（过滤 `system_` 前缀）；validator/processor 也要拦 LLM 直接 start `system_*` 流程。

## 数字人 + TTS（2026-10-07 接入，魔珐星云）
- 形态：**纯前端渲染**，后端只代理下发凭证（AppSecret 只存 `.env`，绝不进前端源码）。
- 后端新增包 `digital_human/`：`tts.py`（edge-tts 封装 + sha256 缓存 + 3 次重试）。
- 后端新增路由 `api/routers/digital_human_router.py`：
  - `GET /api/digital-human/credentials` → `{app_id, app_secret, gateway_server}`；未配置时 **503 + 中文提示**（服务照常启动）。
  - `POST /api/chat/tts` → body `{text, voice?}`，返回 `audio/mpeg`。
- 前端只改了一个文件：`external/customer-service-frontend/src/App.vue`
  - `.workspace` 由两栏改**三栏** `360px minmax(0,1fr) 370px`（≤1600px→`330px/340px`，≤1280px→单栏）。
  - 数字人面板插在 `.chat-card` **之前**（即聊天框左侧），渲染容器 id 固定 `#digital-human-sdk`。
  - `onUnmounted` 必须调 `disconnectDigitalHuman()`，否则服务端房间不释放 → 二次进入撞并发上限（错误码 10005）。
- **`vite.config.js` 无需改**：proxy 规则是 `/api` 前缀，两个新接口都被覆盖。

### ⚠️ 舞台比例必须匹配魔珐应用里的「形象」，且只能实测确定

**结论会随应用变，不要照抄文档也不要照抄上次的结论。** 实测两套应用：

| 魔珐应用的形象（网关 `figure_name`） | 素材形态 | 正确比例 | 9:16 下的表现 |
| --- | --- | --- | --- |
| `SCF25_001`（**当前在用**） | 半身竖版人像、无场景 | **9 / 16** ✅ | 完美居中、头到腰全入画 |
| `jushen_v1_StudyCorner_01`（旧应用） | 1920×1080 横版场景 | 4 / 3 | ❌ 人像被裁出画面，只剩一截手臂 |

SDK 对画面按 `cover` 裁切，**比例选错人像就被裁到画外**，看起来就像「数字人没渲染」。

前端已把它收口成一个变量，换应用只改这一行：
```css
.digital-human-card { --dh-stage-ratio: 9 / 16; }   /* 见 App.vue */
```

**排查手法**：把候选比例（9:16 / 4:3 / 1:1 / 16:9）**逐个真连一次并截图**，别推理。
「舞台里只有背景、没有人」时，先把场景背景图单独下载看一眼 —— 背景里没人就说明人像是独立图层，问题在取景。

### 验证数字人必须用真 Chrome + localhost

- **必须用真 Chrome**：playwright 自带 Chromium 不含 H.264，SDK 的 WebCodecs 解码会报
  `20003 PROCESS_VIDEO_STREAM_ERROR`（卡在 80%）。用
  `executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe"` +
  `--enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader`。
- **必须用 `localhost`**，不能 127.0.0.1 / IP —— 魔珐 SDK 限制。
- 网关 `POST /user/v1/ttsa/session` 返回 **200 且 `error_code:0`** 才说明凭证有效；
  返回体里的 `figure_name` 就是当前形象名，可用来判断该用哪种比例。

### 凭证沿革（便于回退）

- 当前（2026-10-07 晚切换，形象 `SCF25_001`）：`84dab8abe196470a8658f52530d83cb0` / `73baf417dc764b76aac8855ef8e08a06`
- 旧（形象 `jushen_v1_StudyCorner_01`）：`49bf160fd6e24759919bac98bd0c8bb1` / `49da11ba1f3c40028d214ef17fe0eeee`

## 前端主题（2026-10-07 起：浅色清爽版）

- 观感全部由 `external/customer-service-frontend/src/App.vue` 的 `<style scoped>` 决定（**单文件，无外置 CSS、无 UI 库**）。
  深色发光/玻璃拟态版已被**浅色版整体替换**（2026-10-07）。底色 `#f1f4f9`，主色单一 teal `#0d9488`，暖色 `#d97706` 只给价格/待发货。
- **不引 Google Fonts**，用系统字体栈（内网/沙箱会 404）。**没有粒子背景**（`bgCanvas` 那套已整块删除）。
- 图标一律**内联 stroke SVG**，不用 emoji（emoji 在不同 Windows/字体下尺寸与基线都不稳）。
  已样式化选择器：`.clear-button svg` / `.welcome-features svg` / `.tts-button svg` / `.copy-button svg` / `.card-image-placeholder svg`。
- 布局：`.workspace` 三栏 grid `360px minmax(0,1fr) 370px`；**侧栏卡片是两列 grid**（`74px` 缩略图 + 右侧信息，按钮 `grid-column:1/-1`），
  改回 `aspect-ratio` 大图会让单卡涨到 290px、一屏只放 2 张。
- 断点：≤1600 收窄两侧栏，≤1280 **单栏堆叠且用 `order` 让聊天排第一**（`chat-card/digital-human-card/sidebar` = 1/2/3），
  单栏时数字人舞台按**高度**收缩 `height:min(42vh,360px)`（竖版比例下按宽度算会长到 600px+）。

## 客服形象：听澜（2026-10-08 由「小宝」改名）

- 名字定义在 `App.vue` 的 `customerService = { name: '听澜', title: '金牌客服', ... }`；
  另外两处 `alt` 与打字指示「听澜正在输入...」也是硬编码，改名要一起动。
  `conf/config.py` 里 TTS 音色注释提到过这个名字。
- 头像：`src/assets/tinglan.webp`（512×512、37.6 KB、3D 卡通青绿 + 耳麦）。
  生成原图（1024×1024，**带 AI 水印**）留在 `.workbuddy/_avatar/`，要重裁可直接用。
  水印在 x≈880..1015 / y≈935..1015，裁切框 x 上界取 870 就天然避开了。
- 主题色是 teal `#0d9488`，**头像配色要跟它一致**；旧的橙色 `xiaoer.png` 已删（课程资料里还有）。

## ⚠️ 对象卡 payload 有两种形状（历史 ≠ 实时）

- **实时消息**（`appendUserObject`）：payload 是扁平业务对象，`cover_url` / `status` / `amount` 在**顶层**。
- **历史消息**（`appendMessage`，来自 `/api/chat/history`）：payload 是 `{ type, id, title, attributes: {...} }`，值全在 `attributes` 里。
- 模板到处按扁平形状取值（`payload.cover_url`、`payload.status`、`payload.amount`），
  `getObjectAmount / getObjectSummary` 这些辅助函数写了 `payload.x ?? payload.attributes?.x` 兜底，**但模板没有**。
  历史上因此出现「历史里的对象卡没封面图、状态显示成一行文字而不是徽章」。
- 现在在 `appendMessage` 里统一归一：`payload: { ...(object.attributes ?? {}), ...object }`。
  **新增对象字段时记住这个归一，别再在模板里直接取 `attributes`。**

## 本地视觉验收标准动作：`.workbuddy/_visual_check.py`

起 中台18081 + 后端18082 + 前端5173 → playwright（**真 Chrome**）多视口多状态截图 → 全部 terminate，**一个 Python 进程内跑完**。
必须这样做的原因：沙箱 spawn 的子进程在工具调用结束时被回收，分两次调用会测到「进程已死」。
跑法：`"C:\Users\23329\.workbuddy\binaries\python\envs\default\Scripts\python.exe" -u .workbuddy/_visual_check.py`
（**只有这个 venv 装了 playwright**，仓库 `.venv` 和托管 python 3.13 都没有；browsers 在 `~/AppData/Local/ms-playwright`）。
截图落在 `.workbuddy/_shots2/`，runlog 里会打 `console` / `HTTP >=400` 清单。
MySQL 是常驻容器，脚本不负责它；跑之前先 `docker compose -f external/docker/docker-compose.yml up -d mysql`。
改完样式**先 `vite build` 验一遍**（SFC 编译错误会在这里立刻暴露，比看截图快）：
`node node_modules/vite/bin/vite.js build`。

**⚠️ 必须给浏览器显式加代理**：商品的 `cover_url` 全是外链 `https://placehold.co/...`，
沙箱里外网只有走 `http_proxy` 才通，而 **Chrome 不读 `http_proxy` 环境变量** → 不加代理时缩略图全空，
非常容易被误判成 CSS/布局 bug。脚本里已写成
`launch(proxy={"server": os.environ["http_proxy"], "bypass": "localhost,127.0.0.1,::1"})`
—— **`bypass` 不能省**，否则连 `localhost:5173` 都被塞进代理，页面直接白屏。
