# Multiplane 模板（片头 / 参数卡 / 结尾引导）

用 `mf shot --template title|params|endcard --set KEY=值 ...` 出片。
占位符 {{KEY}} 会在渲染前替换；画布 1080×1920（竖屏），按剪辑规范 §9：白字细黑描边、不加底框、不露联系方式、不写价格。
模板本身不带品牌名（品牌隔离 §4.1），品牌行由 --set BRAND= 传。
