# 麦当劳 MCP 接口速查

只列本技能用到的接口。所有接口均为 `mcp__mcd-mcp__` 前缀。

## 一、门店

### query-nearby-stores（到店场景）
```
beType: 1(到店自取) | 5(得来速)
searchType: 1(收藏店, 默认) | 2(按位置搜)
city / keyword: searchType=2 时必填
```
- beType=1 返回的门店**无 beCode**，后续调用不传 beCode
- beType=5 返回的门店**有 beCode**，后续调用必须传 beCode

### delivery-query-addresses → delivery-query-stores（外送场景）
- 先查地址拿 `addressId`，再用 addressId 查可配送门店
- `beType`: 2(麦乐送) | 6(团餐)

## 二、菜单与详情

### query-meals
```
storeCode: 门店编码（必填）
orderType: 1(到店) | 2(外送)
beType: 1|2|5|6
beCode: beType=5/2/6 时必传；beType=1 不传
```
返回在售餐品列表，含 `productCode`、名称、价格、套餐组成、随单购商品。

### query-meal-detail
```
storeCode, orderType, beType, code(=productCode), beCode(按规则)
```
用于查看套餐组成与特调选项（`supportModify`、`modification`、`selectedKey`/`unselectedKey`）。

## 三、优惠券

### query-store-coupons（门店可用券 —— 推荐主用）
```
storeCode, orderType, beType, beCode(按规则)
```
返回**该门店+该订单类型**下可用的券。这是判断"这个方案能不能用券"的权威来源。

### available-coupons（可领取的券）
无参数。返回用户当前**可领取**的"麦麦省"优惠券列表。

### query-my-coupons（卡包已有券）
```
page / pageSize(默认200)
```
返回用户已持有券。**注意**：不校验门店/渠道，能否用于当前订单需以 query-store-coupons 为准。

### auto-bind-coupons（一键领券）
无参数。用户说"帮我领券"时调用，自动领取所有可领券。

## 四、价格计算（核心）

### calculate-price
```
storeCode, orderType, beType, beCode(按规则)
items: [{ productCode, quantity, couponId?, couponCode?, modification?, roundList? }]
needTableware: bool
reservationDate: 预约场景必传 "yyyy-MM-dd HH:mm"
```
- **返回价格单位为「分」，展示时 ÷100**
- 返回 `takeWayList[]`（到店/得来速下单时 `takeWayCode` 来源）
- 计算含券后的实付价，是性价比评分的数据源

**特调 key 规则**：选中项 key=selectedKey；未选中项若 unselectedKey 非空，也必须以 unselectedKey 传入。

## 五、下单

### create-order
```
storeCode, orderType, beType, beCode(按规则)
takeWayCode: orderType=1 时必传（来自 calculate-price）
addressId: orderType=2 时必传
items / needTableware / reservationDate: 同上
```

## 六、营养数据

### list-nutrition-foods
无参数。返回常见餐品的能量(kcal)、蛋白质、脂肪、碳水、钠、钙。
**所有热量/营养引用必须来自此接口。**

## 七、时间

### now-time-info
无参数。返回服务器时间。用于判断"当日"、优惠券有效期、限时活动时间窗。

## 八、参数传递规则总表

| beType | 场景 | orderType | beCode |
|--------|------|-----------|--------|
| 1 | 到店自取 | 1 | 不传 |
| 5 | 得来速 | 1 | 必传（query-nearby-stores） |
| 2 | 麦乐送 | 2 | 必传（delivery-query-stores） |
| 6 | 企业团餐 | 2 | 必传（delivery-query-stores） |

团餐额外：`query-promotions`(满减满折)、`query-meal-assistance`(助餐服务，报 `gmServiceCode` 给 calculate-price)。
