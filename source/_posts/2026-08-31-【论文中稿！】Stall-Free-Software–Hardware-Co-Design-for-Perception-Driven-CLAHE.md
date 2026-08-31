---
title: 【论文中稿！】Stall-Free Software–Hardware Co-Design for Perception-Driven CLAHE
date: 2026-08-31 22:03:27
tags:
  - 论文
  - 算法
  - FPGA
  - 图像增强
categories:
  - docs
cover: https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/%E6%97%A0%E8%81%8C%E8%BD%AC%E7%94%9F.webp?imageSlim
draft: "true"
---
历经九个月终于完成了论文，该论文并不是纸上谈兵，而是从算法到硬件落地闭源/dog

<!-- more -->
## 经历
该项目起源于2025年寒假，最初源自实习公司预研需求，在2025年5月完成CLAHE的优化，之后又花了半年加上了前沿的强化学习和知识蒸馏相关技术，从而实现了能根据场景自动调整CLAHE的FPGA落地算法。

再次特别感谢于老师和共同作者的老师，以及实习公司的张总和李师父！

## 计划
之后未来两个月我会整理相关资料以及技术文档，来阐述和完善这一算法，当前正在搓全链路ISP FPGA 相机，敬请期待！

## 中稿

![image-20260831220411870](https://obsidian-picturebed-1256135654.cos.ap-nanjing.myqcloud.com/obsidion/image-20260831220411870.png?imageSlim)

## 开源仓库
https://github.com/ORI2333/rl-clahe-fpga-artifact
PS：该仓库为大修提供的可复现材料：评估脚本、摘要 CSV 文件、定点输出工具、RTL 代码片段以及诊断性可视化证据。
之后为继续完善完全版本！