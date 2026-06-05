# 环境安装验证报告

**验证日期**: 2026-05-17
**环境**: Windows 11, Python 3.12.10
**虚拟环境**: `e:/2026_AgentStudy/Python_code/.venv/`
**执行者**: 开源研究院+回测引擎部

---

## 1. Qlib 安装验证

| 项目 | 内容 |
|------|------|
| **安装命令** | `pip install pyqlib` |
| **安装结果** | 成功 |
| **安装版本** | pyqlib==0.9.7 |
| **Python 版本兼容性** | cp312 (Python 3.12) 有预编译 wheel，直接下载无需编译 |
| **qlib 版本确认** | `import qlib; qlib.__version__` => `0.9.7` |
| **SCS 编译问题** | 未出现。pyqlib 0.9.7 提供了 `cp312-win_amd64.whl` 预编译包，无需本地编译 SCS。当前环境 SCS==3.2.11 可正常导入。 |
| **补充说明** | qlib 依赖 `pip install qlib` 为旧版本方案，`pyqlib` 是官方推荐安装包名。当前环境使用 `pyqlib` 安装后 import 名为 `qlib`。 |

### 关键依赖
- cvxpy==1.8.2
- lightgbm==4.6.0
- mlflow==3.12.0
- pandas==2.3.3
- numpy==2.4.5

---

## 2. NautilusTrader 安装验证

| 项目 | 内容 |
|------|------|
| **安装命令** | `pip install nautilus_trader` |
| **安装结果** | 成功 |
| **安装版本** | nautilus_trader==1.226.0 |
| **Rust 依赖** | 无需本机安装 Rust 工具链——PyPI 提供了 `cp312-win_amd64.whl` 预编译 wheel，内含 Rust 编译好的 `nautilus_pyo3` 原生模块。 |
| **版本确认** | `import nautilus_trader; nautilus_trader.__version__` => `1.226.0` |
| **模块结构** | 包含 `core` 子模块和 `nautilus_pyo3` 原生扩展模块 |

### 关键依赖
- msgspec==0.21.1
- fsspec==2026.2.0
- portion==2.6.1
- pyarrow==23.0.1
- pytz==2026.2

---

## 3. 依赖库验证

| 库名 | 安装命令 | 版本 | 安装结果 | 备注 |
|------|---------|------|---------|------|
| **empyrical-reloaded** | `pip install empyrical-reloaded` | 0.5.12 | 先前已安装 | import 名为 `empyrical` |
| **riskfolio-lib** | `pip install riskfolio-lib` | 7.2.1 | 先前已安装 | import 名为 `riskfolio` |
| **pyportfolioopt** | `pip install pyportfolioopt` | 1.6.0 | 先前已安装 | import 名为 `pypfopt` |
| **openbb** | `pip install openbb` | 4.7.1 | 先前已安装 | 含多个 provider 扩展包 |
| **pandera** | `pip install pandera` | 0.31.1 | 先前已安装 | — |
| **praw** | `pip install praw` | 7.8.1 | 此次成功安装 | 原环境未安装，现已补充 |

---

## 4. 总结

所有核心框架和依赖库均验证通过：

- **Qlib (pyqlib 0.9.7)**: 安装成功，可正常导入。预编译 wheel 避免了 Windows 上的 SCS 编译问题。
- **NautilusTrader (1.226.0)**: 安装成功，可正常导入。预编译 wheel 包含 Rust 原生模块，无需本地 Rust 工具链。
- **依赖库**: empyrical-reloaded、riskfolio-lib、pyportfolioopt、openbb、pandera 均已预先安装；praw 本次补充安装成功。

**注意事项**:
1. riskfolio-lib 7.2.1 依赖 SCS（3.2.11），该包在当前环境有预编译 wheel，安装正常。
2. nautilus_trader 的 Rust 扩展通过 PyO3 编译在 wheel 中，若未来需从源码构建，则需安装 Rust 工具链（rustup）。
3. openbb 4.7.1 属于旧版架构（provider 分离模式），如需最新版 openbb 统一架构，可参考官方迁移指南。
