---
title: HDMI Display设计手册
date: 2026.04.18
cover: /images/posts/hdmi.webp
tags:
    - ISP
    - FPGA
    - 图像处理
---

## 前置原理补充
### SII9022
这里不做详细介绍，主要侧重如何用FPGA驱动。

基于《LATTICE SiI9022A/SiI9024A HDMI Transmitter Data Sheet 2016》

**Video Input**
- xvYCC metadata support（和sRGB差不多，更宽广的色彩范围）
- BTA-T1004 video input format（没用过）
- Integrated color space converter allows direct connection to all major MPEG decoders, including those that provide only an ITU-R.656 output（单元内置的色彩空间转换器，能处理不同标准（如YUV到RGB）的转换）
- **Internal DE generator supports non-embedded sync formats（DE（数据使能）信号在数字视频中用于标识有效图像数据区域。）**

这里本工程使用**并行数字视频接口** 24-bit RGB 4:4:4 Separate Sync 格式

**HDMI Output**
- HDMI, HDCP, and DVI compatible
- TMDS™ core runs at ==165 MHz==
- Video resolutions up to 1080p and UXGA (72-pin QFN package supports 165 MHz dual-edge mode
- 3D-capable at 720p/60, 1080i/60, and 1080p/24 frame-pack, side-by-side, L + D, and Top-and-Bottom modes
- HDMI Type A, Type-C, and micro-D connector support
**其它：**
支持热插拔

型号特征：
![image.png|700](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260416223535771.png?imageSlim)
**功能框图：**
![image.png|700](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260416223747008.png?imageSlim)

**视频输入转换流程：**
![image.png|800](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260416224216955.png?imageSlim)

**可以倍频**
Video input formats which use a 2x clock (such as YC Mux mode) can then be transmitted across the HDMI link with a 1x clock. Similarly, 1x-to-2x, 1x-to-4x,and 2x-to-4x conversions are possible.

**数据捕获与格式识别：**
以可配置的数据位宽（8/10/12/16/20/24位）捕获RGB或YCbCr视频数据，并根据寄存器设置锁存数据。捕获的**视频格式信息**（如RGB范围、色彩imetry）会被芯片记录下来，并自动插入到后续HDMI数据包的“AVI信息帧”中，供显示设备正确解读，无需主机额外干预

**Embedded Sync Decoding**
提供了三种生成关键时序信号（DE, HSYNC, VSYNC）的方式，以适应几乎所有视频源：
- **直接输入**：最简单的情况，视频源直接提供独立的HSYNC、VSYNC和DE信号。
- **嵌入式同步解码**：针对**ITU-R BT.656**等格式的数字视频流（常见于旧标清设备）。芯片能从视频数据流中内置的SAV/EAV（有效视频开始/结束）代码中，**解码并还原出**HSYNC、VSYNC和DE信号。**这节省了额外的同步信号线。**
- **内部DE生成器**：当视频源只提供HSYNC和VSYNC，却没有DE信号时，芯片可以利用这两个同步信号和像素时钟，**内部生成一个精确的DE信号**。用户可通过寄存器微调DE的活跃区域，以匹配CEA时序规范。**这对于连接许多不输出DE的MPEG解码器至关重要。**

**Video Input  Clock**
![image.png|800](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260417180918149.png?imageSlim)

**Video Input Formats**
采用24bit的 RGB 444格式
![image.png|800](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260417181256092.png?imageSlim)

### VGA / LCD
为什么写VGA，这里VGA/LCD封装的数据非常容易封装为24-bit RGB 4:4:4 Separate Sync 格式，因此这里再介绍一下VGA
#### 接口
|引脚编号|信号名称|功能说明|
|---|---|---|
|1|RED|红色模拟视频信号（0 ~ 0.7V 峰峰值）|
|2|GREEN|绿色模拟视频信号（0 ~ 0.7V 峰峰值）|
|3|BLUE|蓝色模拟视频信号（0 ~ 0.7V 峰峰值）|
|4|ID2 / RES|显示器识别位 2（旧标准用于标识显示器类型，现代多未使用或保留）|
|5|GND (HSYNC)|自测试 / 接地（早期用于自检，现通常接地；部分设备用作 HSYNC 返回地）|
|6|RGND|红色信号地（Red Ground）|
|7|GGND|绿色信号地（Green Ground）|
|8|BGND|蓝色信号地（Blue Ground）|
|9|+5V / KEY|+5V 电源（可选，用于为显示器 EEPROM 供电）或物理防呆键位（部分线缆为空）|
|10|GND (SYNC)|数字地（同步信号公共地）|
|11|ID0 / SDA|显示器识别位 0 / I²C 数据线（DDC 通信，用于读取 EDID 信息）|
|12|ID1 / SCL|显示器识别位 1 / I²C 时钟线（DDC 通信）|
|13|HSYNC|行同步信号（Horizontal Sync）|
|14|VSYNC|场同步信号（Vertical Sync）|
|15|DDC GND|DDC（显示数据通道）地，用于 I²C 通信|
#### 显示原理
**VGA时序标准**
![image.png](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260417214859686.png?imageSlim)

**Hsync 时序**
![image.png](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260417215007905.png?imageSlim)

**VGA时序图**
![image.png|900](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260417214543829.png?imageSlim)
图中的红色区域表示在一个完整的行扫描周期中，Video图像信息只在此区域有效，黄色区域表示在一个完整的场扫描周期中，Video图像信息只在此区域有效，两者相交的橙色区域，就是VGA图像的最终显示区域。

**VGA显示模式**
这里只是放在这里，和项目无关
![image.png](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260417234220162.png?imageSlim)
行扫描周期 \* 场扫描周期 \* 刷新频率 = 时钟频率


## 工程
### 接口
```systemverilog
module hdmi_display(
    // global clock
    input                               clk                        ,
    input                               rst_n                      ,

    //lcd interface
    output                              lcd_clk                    ,
    output                              lcd_hs                     ,
    output                              lcd_vs                     ,
    output                              lcd_de                     ,

    output               [   7: 0]      lcd_red                    ,
    output               [   7: 0]      lcd_green                  ,
    output               [   7: 0]      lcd_blue                    
);
```

### 系统上电时钟
代码见：`hdmi_display\rtl\sys_clk_ctrl.sv`
功能：延时50ms保证时钟稳定
关键时序设计：
![wavedrom.svg](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/wavedrom.svg?imageSlim)
目标分辨率为720p，这里使用74.25MHz时钟
这里使用了clock wizard IP核
**IP：**
![image.png|800](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260416230948486.png?imageSlim)

### lCD/VGA 驱动
代码见：`hdmi_display\rtl\lcd_driver.sv`
关键时序设计：
![image.png](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/20260418160047140.png?imageSlim)

### 时钟转发
解决时钟网络无法直接连到普通 I/O 引脚的问题
采用ODDR
参考[[ODDR（Xilinx 原语）]]说明
这里设计为：
```verilog
ODDR #(
    .DDR_CLK_EDGE        ("OPPOSITE_EDGE"           ),// "OPPOSITE_EDGE" or "SAME_EDGE" 
    .INIT                (1'b0                      ),// Initial value of Q: 1'b0 or 1'b1
    .SRTYPE              ("SYNC"                    ) // Set/Reset type: "SYNC" or "ASYNC" 
   ) ODDR_inst (
    .Q                   (lcd_dclk                  ),// 1-bit DDR output
    .C                   (lcd_dclk_reg              ),// 1-bit clock input
    .CE                  (1'b1                      ),// 1-bit clock enable input
    .D1                  (1'b1                      ),// 1-bit data input (positive edge)
    .D2                  (1'b0                      ),// 1-bit data input (negative edge)
    .R                   (1'b0                      ),// 1-bit reset
    .S                   (1'b0                      ) // 1-bit set
   );
```
### 显示测试
使用
```
Author              :       CrazyBingo
Technology blogs    :       www.crazyfpga.com
```
## 测试结果
![测试结果.jpg](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/%E6%B5%8B%E8%AF%95%E7%BB%93%E6%9E%9C.jpg?imageSlim)

## 源码
https://github.com/ORI2333/FPGA_ISP/tree/main/hdmi_display
如果对你有用，请帮忙给个Star！😘