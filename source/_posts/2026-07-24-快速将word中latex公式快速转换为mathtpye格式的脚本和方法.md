---
title: '快速将 Word 中 LaTeX 公式批量转为 MathType 的脚本与方法（Python）'
date: '2026-07-24 00:17:24'
tags:
  - Word
  - MathType
  - LaTeX
  - Python
  - 专利写作
  - Windows自动化
categories:
  - docs
cover: https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260729225101944.png?imageSlim
draft: false
---

写专利或论文 Word 稿时，公式常以 `$...$` 文本存在；正式提交前往往要变成 **MathType** 对象。

<!-- more -->

本文记录一套以 **Python** 为主的落地方法：需求从哪来、为什么用「模拟快捷键」而不是整篇黑盒转换、实现要点、使用步骤，以及 MathType 忙时如何避免把 Word 撑爆。

## 1. 需求从哪来

### 1.1 典型场景

- 中文 **发明专利** 说明书 / 权利要求书公式很多  
- 写作阶段用 `$LaTeX$` 便于改稿、和论文源对齐、批量替换  
- 代理或排版要求最终为 **MathType**（可编辑公式对象）  
- 数量从几十到几百，纯手选再转不可持续  

### 1.2 真正卡住的不是“会不会 TeX”

MathType 7.x 自带 **Toggle TeX**（常见 **`Alt+\`**）：选中 `$x+y$` 就能变公式。  
难的是 **节奏**：

1. 找到下一处 `$...$`  
2. 精确选中（含两端 `$`）  
3. 触发 Toggle TeX  
4. **等 MathType 做完**，再处理下一处  

人若连按太快，会出现：

```text
Only One MathType command can be executed at a time.
Please try again later.
```

此时若继续批量按键，命令叠在一起，Word / MathType 容易卡住，内存持续上涨——看起来像“内存泄漏”，本质是 **命令重入 + 对话框堆积**。

### 1.3 目标

| 目标 | 说明 |
|------|------|
| 少动手 | 一键「选中 + 转换 + 等待」 |
| 可控 | 单次 / 批量 / 暂停 / 停止 |
| 安全 | MathType 忙时 **立刻停**，禁止继续发命令 |
| 可迁移 | 其它 Windows 电脑也能用（exe 或 Python 源码） |
| 主技术栈 | **Python 3 标准库**（不依赖 AutoHotkey） |

## 2. 总体方法：人机协同，而不是重写公式引擎

我们没有去解析整篇 docx、也没有自己渲染公式，而是用 **Python 模拟已经调通的快捷键**：

```text
┌──────────────┐    Alt+]     ┌──────────────┐
│ Python 助手   │ ──────────► │ Word 选区宏   │  选中下一处 $...$
└──────────────┘              └──────────────┘
        │
        │ 立刻 Alt+\
        ▼
┌──────────────┐
│   MathType   │  Toggle TeX
└──────────────┘
        │
        │ 等待 N 秒 + 轮询“忙对话框”
        ▼
    下一处 / 停止
```

**为什么这样设计：**

1. **复用已验证链路**  
   本机 Word 宏 + MathType 一旦手动能通，脚本只负责“按得又稳又有节奏”。  
2. **不碰文档二进制**  
   不直接改 docx XML / OLE，降低损坏风险。  
3. **边界清晰**  
   - 公式写得对不对、MT 认不认 → 写作与预处理  
   - 点得勤不勤、会不会叠命令 → Python 助手  

（实现上曾考虑过 AutoHotkey，但最终主路径选定 **Python**：便于调试、带 tkinter 控制面板、和 Anaconda 工作流一致，且标准库即可打包 exe。）

## 3. 三个组件

### 3.1 Word 宏：选中下一处 `$...$`

- 从当前光标向后找 `$` … `$` 并整段选中  
- **找不到时不要 Wrap 回文档开头**（否则批量次数过大会反复扫全文）  
- 绑定 **`Alt+]`**，保存到 **Normal.dotm**  
- 仓库：`src/SelectNextDollarFormula.bas`

### 3.2 MathType：Toggle TeX

- 选中 `$...$` 后 **`Alt+\`**  
- MathType 7.8 的 TeX **不是完整 LaTeX**，易出 `?` 时需预处理，例如：

| 不友好 | 更稳 |
|--------|------|
| `\operatorname{clip}` | `\mathrm{clip}` |
| `\mathbb{R}` | `\mathrm{R}` |
| `$[1][64]$` | `$1\times 64$` |
| `$[1.0,10.0]$` | `$\left[1.0,\ 10.0\right]$` |

建议正文统一 **单美元** `$...$`。

### 3.3 Python 助手：按键 + 等待 + 忙检测

主程序：`src/select_and_convert_formula.py`（stdlib + ctypes + tkinter）

| 能力 | 说明 |
|------|------|
| 模拟按键 | `SendInput`（修正 64 位结构）；失败回退 `keybd_event` |
| 正确节奏 | `Alt+]` → **立刻** `Alt+\` → **等待**转换完成 → 下一处 |
| UI | 置顶：单次 / 开始 / 暂停 / 停止；热键 Ctrl+Alt+] / S / P / X / Q |
| 忙检测 | 枚举窗口文本，匹配 *Only One MathType command…* 后 **停止批量** |
| 窗口尺寸 | 不误用 `SW_RESTORE` 把最大化 Word 缩成普通窗口 |

可选：`src/select_and_convert_formula.ps1`（PowerShell 备选，功能子集）。

## 4. 实现时踩过的坑

### 4.1 用 COM 数 `$` 猜“扫完了”

曾在每次选中后统计正文 `$` 或检查选区。结果：

- 误判 → **转 1 处就报没有更多**  
- 甚至在 `Alt+\` 前 return → **完全不转**  

结论：**不要用不可靠的 COM 猜结束**。结束交给次数、用户停止、或 MathType 忙。

### 4.2 等待放错位置

错误：`选中 → 等很久 → 转换 → 马上下一处`  
正确：`选中 → 立刻转换 → 等 1～2s → 下一处`  

### 4.3 `ShowWindow(SW_RESTORE)` 缩小窗口

最大化 Word 会被还原成普通尺寸。应仅在最小化时 Restore。

### 4.4 宏 Wrap + 批量次数过大

找不到还从头找 → 反复 Toggle → 内存与卡顿。宏必须 `wdFindStop`。

### 4.5 宏信任与快捷键保存位置

- 宏在 Normal ≠ 快捷键在 Normal  
- 信任中心禁用宏时，表现会像“快捷键坏了”  

## 5. 使用步骤

### 5.1 准备

1. Word + MathType 7.x  
2. 安装选区宏 → `Alt+]`  
3. 手测 `Alt+\` 能转 `$x+y$`  
4. 公式尽量 `$...$`，并做过 MT 友好清洗  

### 5.2 运行 Python 助手

```bat
cd word-latex-to-mathtype
python src\select_and_convert_formula.py --ui
```

或双击 `run_formula_ui.bat`；有 `dist\WordLatexToMathType.exe` 时优先运行 exe。

### 5.3 转换

1. 打开 docx，点正文  
2. 输入法 **英文**  
3. 「转换后等待」**1.5～2.5** 秒  
4. 先 **单次**，再 **批量**  

| 操作 | 热键 |
|------|------|
| 单次 | Ctrl+Alt+] |
| 开始批量 | Ctrl+Alt+S |
| 暂停/继续 | Ctrl+Alt+P |
| 停止 | Ctrl+Alt+X |
| 退出 | Ctrl+Alt+Q |

### 5.4 MathType 忙

1. 脚本应已自动停  
2. 关对话框，等数秒  
3. **单次**从当前位置继续  
4. 加大等待；**不要从头连按**  
### 详细步骤
1. alt + F11新建宏使用仓库里的宏代码，保存到normal模板中![image.png](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260729224106560.png?imageSlim)
2. alt + F8 测试运行
3. 文件→选项→自定义功能区→键盘快捷方式→自定义![image.png](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260729224303611.png?imageSlim)
4. 绑定宏快捷键![image.png](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260729224355105.png?imageSlim)
5. 测试`Alt + [` 指令
6. 图形化运行![image.png](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260729224514226.png?imageSlim)
7. 查找$\frac{\frac{数量，/2即可，前提要鼠标光标放到第一个`\$`前，随便找个位置点击mathtype（提前打开）默认情况下初始化比较慢，这是mathtype的问题，之后再开始批量开始 


## 6. 打包给别的电脑

源码无 pip 依赖：

```bat
pip install pyinstaller
cd src
pyinstaller --noconfirm --onefile --console --name WordLatexToMathType select_and_convert_formula.py
```

把 `WordLatexToMathType.exe` 拷到其它 Windows 即可。  
**目标机仍需安装 Word + MathType**，并配置好 `Alt+]` / `Alt+\`。

## 7. 方法边界

| 能做 | 不能指望 |
|------|----------|
| 批量触发选中 + Toggle TeX | 任意复杂 LaTeX 100% 一次可渲染 |
| 控制节奏、忙时停止 | 替代 MathType 安装与授权 |
| 降低重复劳动 | 免去人工抽查 |

## 8. 小结

> **用 Python 当节拍器，用 Word 宏找下一处，用 MathType 做渲染。**

在专利 Word 实务里，这比“写全能公式转换器”更快落地：先保证两键手动能通，再交给脚本跑节奏；忙了就停，闲了再续。

## 仓库

- <https://github.com/ORI2333/word-latex-to-mathtype>  
- 主路径：**Python**；PowerShell 仅备选。  
