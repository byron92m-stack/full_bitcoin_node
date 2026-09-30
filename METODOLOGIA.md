# Convenciones de OBM v0.1.0

Extraido de los 23 README.md oficiales (repo diegorllanos/open-bitcoin-metrics, rama main).


---

## obm_block_count_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_block_count_daily` |
| Display name | Daily Bitcoin block count |
| Unit | `blocks` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Bitcoin Core full node |
| External data required | No |
| Main use | Block production, network operation, normalization of block-level metrics |

### Definicion
Let \(B_d\) denote the set of Bitcoin blocks assigned to UTC calendar day \(d\). The daily block count is defined as:

```text
BlockCount_d = |B_d|
```

where \(|B_d|\) is the number of blocks whose timestamps fall within UTC calendar day \(d\).

A block is assigned to a day according to the UTC date derived from the block timestamp returned by Bitcoin Core.

### Menciones de redondeo / frontera temporal
- However, the realized number of blocks per UTC day fluctuates because block discovery is probabilistic, mining difficulty adjusts only periodically, and block timestamps do not necessarily align with exact calendar boundaries.
- The script uses a safety height margin around the estimated date interval because Bitcoin block timestamps are not strictly monotonic in block height. This reduces the risk of missing blocks near daily boundaries.
- 10678 seconds (around three hours).
- External comparisons should be interpreted cautiously because providers may use different timestamp conventions, reorganization policies, or daily-boundary rules.


---

## obm_block_weight_wu_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_block_weight_wu_daily` |
| Display name | Daily block weight in weight units |
| Unit | `WU` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Direct Bitcoin Core block scan |
| External data required | No |
| Main use | Block-space usage, fee-market analysis, normalization of transaction activity |

### Definicion
`obm_block_weight_wu_daily` measures the total block weight of all Bitcoin blocks assigned to a given UTC calendar day.

Let `B_d` denote the set of blocks assigned to UTC date `d`. For each block `b`, let:

```text
Weight_b
```

denote its block weight in Bitcoin weight units, as returned by Bitcoin Core.

The metric is defined as:

```text
BlockWeightWU_d =
    sum over b in B_d Weight_b
```

A block is assigned to a UTC calendar date using its block timestamp as returned by Bitcoin Core:

```text
d(b) = UTCDate(block_time_b)
```

The unit is:

```text
WU
```

where `WU` denotes Bitcoin weight units.

### Menciones de redondeo / frontera temporal
- `obm_block_weight_wu_daily` measures the total amount of block weight included in the Bitcoin main chain on each UTC day. It is a block-space usage metric.
- The height-margin expansion is used because Bitcoin block timestamps are not strictly monotonic with respect to block height. The expanded scan interval reduces the risk of missing boundary blocks whose timestamps fall inside the selected UTC dates.
- - may differ from provider series that smooth the data or use different daily boundaries.


---

## obm_cdd_age_band_btcxdays_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_cdd_age_band_btcxdays_daily` |
| Display name | Daily Bitcoin Days Destroyed by age band |
| Unit | `BTC-days` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Exported from `obm_spent_output_indexer.sqlite` |
| External data required | No |
| Output shape | Wide table, one row per date, one column per age band |
| Main use | CDD age decomposition, dormant-supply analysis, validation of aggregate CDD |

### Definicion
`obm_cdd_age_band_btcxdays_daily` decomposes daily Bitcoin Days Destroyed by the age of the outputs at the moment they are spent.

For each spent output `i`, let:

```text
ValueBTC_i
```

be the BTC value of the previous output being spent, and let:

```text
AgeDays_i
```

be the age of that previous output, measured as the elapsed time in days between the block in which the output was created and the block in which it is spent.

For each UTC day `d` and age band `k`, the metric reports:

```text
CDDAgeBandBTCxDays_{d,k}
    = sum_i ValueBTC_i * AgeDays_i * 1{AgeDays_i belongs to band k}
```

where the sum is taken over all outputs spent in blocks assigned to UTC calendar day `d`.

The unit is:

```text
BTC-days
```

This metric is not a scalar daily series. It is a wide daily age-band table: each row corresponds to one UTC date, and each age-band column contains the CDD contributed by outputs assigned to that band.

The standard OBM daily calendar starts on `2009-01-01`; release exports should not use 
earlier `--start_date` values.

### Menciones de redondeo / frontera temporal
- For each UTC day `d` and age band `k`, the metric reports:
- The indexer stores age-band CDD internally as satoshi-days. The exporter converts each value to BTC-days and writes values with twelve decimal places:
- The additional decimal precision is useful because CDD can include fractional-day ages.
- - verifies that all CDD age-band values are present and parseable as decimals;
- External comparisons should be interpreted cautiously because providers may differ in timestamp convention, age-band boundaries, fractional-day treatment, entity adjustment, change-output treatment, transfer-value definition, and historical edge-case handling.
- - uses fixed age-band boundaries;


---

## obm_cdd_btcxdays_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_cdd_btcxdays_daily` |
| Display name | Bitcoin Days Destroyed |
| Unit | `BTC-days` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Exported from `obm_spent_output_indexer.sqlite` |
| External data required | No |
| Main use | Coin-age activity, dormant-coin movement, UTXO-age analysis |

### Definicion
Bitcoin Days Destroyed measures the value-weighted age of coins spent on a given day.

For each spent output `i`, let:

```text
ValueBTC_i
```

be the BTC value of the previous output being spent, and let:

```text
AgeDays_i
```

be the time, measured in days, between the creation of that previous output and the block in which it is spent.

The CDD contribution of spent output `i` is:

```text
CDD_i = ValueBTC_i * AgeDays_i
```

Daily Bitcoin Days Destroyed is the sum of these contributions over all outputs spent in blocks assigned to UTC calendar day `d`:

```text
CDD_d = sum_i ValueBTC_i * AgeDays_i
```

where the sum is taken over all spent outputs assigned to day `d`.

The unit is:

```text
BTC-days
```

For example, spending 2 BTC that have remained unspent for 100 days contributes:

```text
2 * 100 = 200 BTC-days
```

### Menciones de redondeo / frontera temporal
- - studying coin-age dynamics around market cycles, halvings, or stress periods.
- The indexer stores CDD internally as a decimal satoshi-day value. The exporter converts this to BTC-days and writes values with eight decimal places:
- The eight-decimal output convention is consistent with BTC-denominated OBM series while preserving reproducible daily CDD values.


---

## obm_cdd_per_supply_days_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_cdd_per_supply_days_daily` |
| Display name | Bitcoin Days Destroyed per Unit of Supply |
| Unit | `days` |
| Frequency | `daily` |
| Time convention | UTC calendar day, inherited from the input OBM series |
| Source layer | Derived from existing OBM CSV files |
| External data required | No |
| Required OBM inputs | `obm_cdd_btcxdays_daily`, `obm_supply_btc_daily` |
| Main use | Supply-normalized coin-age destruction, dormant-supply activation, long-run comparability of CDD |

### Definicion
Let \(CDD_d\) denote daily Bitcoin Days Destroyed on UTC calendar day \(d\), measured in BTC-days, and let \(S_d\) denote the outstanding Bitcoin supply on the same date, measured in BTC. The Bitcoin Days Destroyed per Unit of Supply series is defined as:

```text
CDDPerSupply_d = CDD_d / S_d
```

where:

```text
CDD_d = value of obm_cdd_btcxdays_daily on date d
S_d   = value of obm_supply_btc_daily on date d
```

The resulting unit is:

```text
BTC-days / BTC = days
```

If the supply value is zero, the output value is recorded as missing rather than zero, because the ratio is undefined.

### Menciones de redondeo / frontera temporal
- Output values are written with 12 decimal places. Missing values are written as empty fields.
- - inspect unusually large observations, since they may reflect genuine old-coin movement, data-boundary effects, or issues inherited from the source CDD series.


---

## obm_difficulty_eod_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_difficulty_eod_daily` |
| Display name | End-of-day Bitcoin mining difficulty |
| Unit | `difficulty` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Direct Bitcoin Core block scan |
| External data required | No |
| Main use | Mining conditions, protocol state, difficulty-retarget analysis, hashrate-related studies |

### Definicion
`obm_difficulty_eod_daily` measures the Bitcoin mining difficulty observed at the end of each UTC calendar day, under the OBM block-timestamp convention.

Let `B_d` denote the set of blocks assigned to UTC date `d`. For each block `b`, let:

```text
height_b
```

be the block height, and let:

```text
Difficulty_b
```

be the mining difficulty reported by Bitcoin Core for that block.

The metric is defined as:

```text
DifficultyEOD_d =
    Difficulty_b*
```

where:

```text
b* = argmax_{b in B_d} height_b
```

That is, `b*` is the highest-height block among all blocks assigned to UTC date `d`.

A block is assigned to a UTC calendar date using its block timestamp as returned by Bitcoin Core:

```text
d(b) = UTCDate(block_time_b)
```

If no block is assigned to date `d`, the value is undefined and is written as:

```text
NaN
```

The standard OBM daily calendar starts on `2009-01-01`; release exports should not use 
earlier `--start_date` values.

### Menciones de redondeo / frontera temporal
- An alternative would be an average daily difficulty across blocks assigned to a date, but that would be less natural for a stepwise protocol variable. Difficulty remains constant during a difficulty epoch and changes only at retarget boundaries. The end-of-day convention records the difficulty state reached by the end of the UTC date.
- The height-margin expansion is used because Bitcoin block timestamps are not strictly monotonic with respect to block height. The expanded scan interval reduces the risk of missing boundary blocks whose timestamps fall inside the selected UTC dates.
- Bitcoin Core returns difficulty as a JSON numeric value. The script parses this value using Python's `Decimal` type and writes defined observations with twelve decimal places.
- - verify that difficulty remains constant within ordinary retarget periods and changes at difficulty-adjustment boundaries;
- - inspect unusually large changes and confirm that they coincide with retarget boundaries;
- External comparisons should be interpreted cautiously because providers may differ in timestamp convention, daily boundary rules, whether they report end-of-day difficulty, average difficulty, or forward-filled difficulty, and how they handle dates with no blocks.


---

## obm_dormancy_days_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_dormancy_days_daily` |
| Display name | Daily dormancy |
| Unit | `days` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Exported from `obm_spent_output_indexer.sqlite` |
| External data required | No |
| Main use | Average age of spent value, coin-age analysis, dormant-supply activity |

### Definicion
`obm_dormancy_days_daily` measures the value-weighted average age, in days, of outputs spent on a given UTC calendar day.

For each spent output `i`, let:

```text
ValueBTC_i
```

be the BTC value of the previous output being spent, and let:

```text
AgeDays_i
```

be the age of that previous output, measured as the elapsed time in days between the block in which the output was created and the block in which it is spent.

Bitcoin Days Destroyed for the day is:

```text
CDD_d = sum_i ValueBTC_i * AgeDays_i
```

Daily spent value is:

```text
SpentValueBTC_d = sum_i ValueBTC_i
```

Dormancy is defined as:

```text
DormancyDays_d = CDD_d / SpentValueBTC_d
```

for dates where `SpentValueBTC_d` is positive.

The unit is:

```text
days
```

because BTC-days divided by BTC leaves days.

The standard OBM daily calendar starts on `2009-01-01`; release exports should not use earlier `--start_date` values.

### Menciones de redondeo / frontera temporal
- The exporter writes defined dormancy values with twelve decimal places:
- This is a ratio measured in days. The twelve-decimal output convention preserves more precision than is usually needed for interpretation, while keeping the CSV representation stable and reproducible.


---

## obm_est7d_hashrate_ehs_daily

### Resumen
| Field | Value |
|---|---|
| Canonical series identifier | `obm_est7d_hashrate_ehs_daily` |
| Display name | Estimated 7-day network hashrate in EH/s |
| Unit | `EH/s` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Direct Bitcoin Core block-metadata scan |
| External data required | No |
| Default window | 7 trailing calendar days |
| Main use | Mining activity, network security proxy, difficulty and miner-incentive analysis |

### Definicion
`obm_est7d_hashrate_ehs_daily` estimates the Bitcoin network hashrate from block difficulty and realized block production.

Hashrate is not directly observed on-chain. It must be inferred from the amount of proof-of-work implied by blocks found over a time interval.

For each UTC date `d`, the canonical 7-day window is the trailing interval ending at 23:59:59 UTC on date `d`:

```text
W_d = blocks with timestamps in [d - 6 days 00:00:00 UTC, d 23:59:59 UTC]
```

For each block `b` in the window, let:

```text
Difficulty_b
```

be the mining difficulty reported by Bitcoin Core for that block.

The estimated hashrate in hashes per second is:

```text
EstimatedHashrateHPS_d =
    sum_{b in W_d} Difficulty_b * 2^32
    /
    elapsed_seconds_d
```

where:

```text
elapsed_seconds_d =
    max block timestamp in W_d - min block timestamp in W_d
```

The value is converted to exahashes per second as:

```text
EstimatedHashrateEHS_d =
    EstimatedHashrateHPS_d / 10^18
```

The output unit is:

```text
EH/s
```

### Menciones de redondeo / frontera temporal
- A one-day estimate would be very noisy because Bitcoin block discovery is probabilistic. A UTC day may contain more or fewer blocks than expected even if the underlying hashrate is unchanged.
- The height-margin expansion is used because Bitcoin block timestamps are not strictly monotonic with respect to block height. The expanded scan interval reduces the risk of missing boundary blocks whose timestamps fall inside the rolling windows.
- Difficulty values are parsed using Python's `Decimal` type. The script computes the estimated hashrate using high-precision decimal arithmetic:
- Defined output values are written with twelve decimal places.
- - inspect the effect of retarget boundaries on the estimate.
- The metric should not be derived directly from `obm_difficulty_eod_daily`, because the hashrate estimate needs block-level difficulty over the full rolling window, especially around retarget boundaries.


---

## obm_fee_share_revenue_ratio_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_fee_share_revenue_ratio_daily` |
| Display name | Fees as share of miner revenue |
| Unit | `ratio` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Derived from `obm_fees_btc_daily` and `obm_issuance_btc_daily` |
| External data required | No |
| Main use | Fee substitution, security budget, subsidy-to-fee transition |

### Definicion
Let `FeesBTC_d` denote the total transaction fees paid in BTC on UTC calendar day `d`, as reported by:

```text
obm_fees_btc_daily
```

Let `Issuance_d` denote the realized Bitcoin issuance on UTC calendar day `d`, as reported by:

```text
obm_issuance_btc_daily
```

Miner revenue in BTC is the sum of issuance and fees:

```text
MinerRevenueBTC_d = Issuance_d + FeesBTC_d
```

The fee share of miner revenue is defined as:

```text
FeeShare_d = FeesBTC_d / (Issuance_d + FeesBTC_d)
```

The metric is reported as a ratio, not as a percentage. For example:

```text
FeeShare_d = 0.025
```

means that transaction fees accounted for 2.5% of BTC-denominated miner revenue on that date.

### Menciones de redondeo / frontera temporal
- - evaluating the economic significance of transaction fees around congestion episodes;
- field with twelve decimal places:


---

## obm_fees_btc_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_fees_btc_daily` |
| Display name | Daily transaction fees in BTC |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Exported from `obm_spent_output_indexer.sqlite` |
| External data required | No |
| Main use | Fee-market activity, miner incentives, security-budget analysis |

### Definicion
`obm_fees_btc_daily` measures the total transaction fees paid by non-coinbase transactions included in blocks assigned to a given UTC calendar day.

For each non-coinbase transaction `j`, the transaction fee is computed as:

```text
fee_j = input_value_j - output_value_j
```

where:

```text
input_value_j
```

is the total value of the previous outputs spent by the transaction inputs, and:

```text
output_value_j
```

is the total value of the transaction outputs.

Daily transaction fees are obtained by summing all transaction fees over all non-coinbase transactions included in blocks assigned to UTC calendar day `d`:

```text
FeesBTC_d = sum_j fee_j
```

where the sum is taken over all non-coinbase transactions assigned to day `d`.

### Menciones de redondeo / frontera temporal
- The indexer stores transaction fees internally as integer satoshis. The exporter converts this value to BTC and writes values with eight decimal places:
- This preserves the standard Bitcoin monetary precision.


---

## obm_issuance_btc_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_issuance_btc_daily` |
| Display name | Daily Bitcoin issuance |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Exported from `obm_spent_output_indexer.sqlite` |
| External data required | No |
| Main use | Monetary issuance, subsidy dynamics, supply-growth analysis |

### Definicion
Let `B_d` denote the set of Bitcoin blocks assigned to UTC calendar day `d`. For each block `b`, let:

```text
CoinbaseOutput_b
```

denote the total output value of the coinbase transaction in that block, measured in BTC, and let:

```text
Fees_b
```

denote the total transaction fees paid by non-coinbase transactions in that block, also measured in BTC.

Realized issuance in block `b` is defined as:

```text
Issuance_b = CoinbaseOutput_b - Fees_b
```

Daily realized issuance is then:

```text
Issuance_d = sum_{b in B_d} Issuance_b
```

A block is assigned to a day according to the UTC date derived from the block timestamp returned by Bitcoin Core.

This definition separates newly issued BTC from transaction fees. The coinbase transaction pays miners both newly issued BTC and transaction fees, but fees are transfers of already existing BTC. Therefore, the newly issued component is obtained by subtracting transaction fees from the total coinbase output value.

### Menciones de redondeo / frontera temporal
- - analyzing subsidy reductions around halving events;
- The exporter writes the `value` field with eight decimal places:
- This matches the BTC-denominated precision convention used by other OBM series.
- - check that values drop around subsidy halving periods;
- up to exact decimal representation.


---

## obm_liveliness_ratio_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_liveliness_ratio_daily` |
| Display name | Daily liveliness ratio |
| Unit | `ratio` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Derived from existing OBM CSV files |
| External data required | No |
| Main use | Cumulative coin-age utilization, holding/spending dynamics, macro on-chain activity |

### Definicion
`obm_liveliness_ratio_daily` is defined as the ratio between cumulative Bitcoin Days Destroyed and cumulative coin-days created.

For each UTC date `d`:

```text
Liveliness_d =
    CumulativeCDD_d / CumulativeCoinDaysCreated_d
```

where:

```text
CumulativeCDD_d =
    sum_{tau <= d} CDD_tau
```

and:

```text
CumulativeCoinDaysCreated_d =
    sum_{tau <= d} SupplyBTC_tau
```

In OBM series terms:

```text
CumulativeCDD_d =
    cumulative sum of obm_cdd_btcxdays_daily
```

and:

```text
CumulativeCoinDaysCreated_d =
    cumulative sum of obm_supply_btc_daily
```

This implementation uses daily Bitcoin supply as the daily coin-day creation base. It is therefore a transparent daily approximation of the cumulative coin-day creation process.

The output unit is:

```text
ratio
```

### Menciones de redondeo / frontera temporal
- The script uses Python's `Decimal` type with high precision when accumulating source series and computing the ratio.
- Defined output values are written with twelve decimal places:
- - verifies that all source `value` fields are present and parseable as decimals;
- - verify that the liveliness ratio changes smoothly except around days with unusually large CDD;


---

## obm_miner_revenue_btc_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_miner_revenue_btc_daily` |
| Display name | Daily miner revenue in BTC |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Exported from `obm_spent_output_indexer.sqlite` |
| External data required | No |
| Main use | Miner compensation, security-budget analysis, fee and issuance decomposition |

### Definicion
`obm_miner_revenue_btc_daily` measures the total BTC paid to miners through coinbase transactions in blocks assigned to a given UTC calendar day.

For each block `b`, miner revenue in BTC is the total output value of the coinbase transaction:

```text
MinerRevenueBTC_b = CoinbaseOutputBTC_b
```

Daily miner revenue is obtained by summing this quantity over all blocks assigned to UTC calendar day `d`:

```text
MinerRevenueBTC_d = sum_b CoinbaseOutputBTC_b
```

where the sum is taken over all blocks assigned to day `d`.

The coinbase transaction pays miners two components:

```text
MinerRevenueBTC_d = IssuanceBTC_d + FeesBTC_d
```

where:

- `IssuanceBTC_d` is newly created BTC;
- `FeesBTC_d` is BTC paid by users as transaction fees.

### Menciones de redondeo / frontera temporal
- The indexer stores coinbase output values internally as integer satoshis. The exporter converts this value to BTC and writes values with eight decimal places:
- This preserves the standard Bitcoin monetary precision.


---

## obm_raw_output_value_btc_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_raw_output_value_btc_daily` |
| Display name | Daily raw output value in BTC |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Exported from `obm_spent_output_indexer.sqlite` |
| External data required | No |
| Main use | Raw on-chain output activity, transaction-output volume, gross settlement diagnostics |

### Definicion
`obm_raw_output_value_btc_daily` measures the total BTC value of outputs created by non-coinbase transactions in blocks assigned to a given UTC calendar day.

For each non-coinbase transaction `j`, let:

```text
OutputValueBTC_j
```

be the sum of the BTC values of all outputs created by that transaction.

Daily raw output value is:

```text
RawOutputValueBTC_d =
    sum_j OutputValueBTC_j
```

where the sum is taken over all non-coinbase transactions included in blocks assigned to UTC date `d`.

Coinbase transaction outputs are excluded. Therefore, this metric measures ordinary transaction-output creation and does not include miner subsidy or fee payments created through the coinbase transaction.

The unit is:

```text
BTC
```

### Menciones de redondeo / frontera temporal
- and writes values with eight decimal places.
- When BTC-denominated columns are used, the exporter relies on decimal arithmetic. This is supported for flexibility, but satoshi-denominated columns are preferred because they avoid rounding ambiguity.
- - verifies that numeric values can be parsed as valid decimals;
- up to formatting precision;


---

## obm_spent_output_count_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_spent_output_count_daily` |
| Display name | Daily spent output count |
| Unit | `outputs` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Exported from `obm_spent_output_indexer.sqlite` |
| External data required | No |
| Main use | UTXO-flow activity, input-side activity, spent-output analysis |

### Definicion
`obm_spent_output_count_daily` measures the number of previous outputs spent by non-coinbase transaction inputs in blocks assigned to a given UTC calendar day.

For each non-coinbase transaction input, the indexer resolves the input to the previous output it spends. Each successfully spent previous output contributes one unit to the daily count.

The metric is defined as:

```text
SpentOutputCount_d = count_i(SpentOutput_i)
```

where the count is taken over all previous outputs spent by non-coinbase transaction inputs assigned to UTC calendar day `d`.

The unit is:

```text
outputs
```

### Menciones de redondeo / frontera temporal
- The metric is an integer count. The exporter writes values without decimal places:


---

## obm_spent_value_age_band_btc_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_spent_value_age_band_btc_daily` |
| Display name | Daily spent output value by age band in BTC |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Exported from `obm_spent_output_indexer.sqlite` |
| External data required | No |
| Output shape | Wide table, one row per date, one column per age band |
| Main use | Age composition of spent value, UTXO-flow analysis, validation of threshold metrics |

### Definicion
`obm_spent_value_age_band_btc_daily` decomposes total daily spent output value by the age of the outputs at the moment they are spent.

For each spent output `i`, let:

```text
ValueBTC_i
```

be the BTC value of the previous output being spent, and let:

```text
AgeDays_i
```

be the age of that previous output, measured as the elapsed time in days between the block in which the output was created and the block in which it is spent.

For each UTC day `d` and age band `k`, the metric reports:

```text
SpentValueAgeBandBTC_{d,k}
    = sum_i ValueBTC_i * 1{AgeDays_i belongs to band k}
```

where the sum is taken over all outputs spent in blocks assigned to UTC calendar day `d`.

The unit is:

```text
BTC
```

This metric is not a scalar daily series. It is a wide daily age-band table: each row corresponds to one UTC date, and each age-band column contains the BTC value of spent outputs assigned to that band.

### Menciones de redondeo / frontera temporal
- For each UTC day `d` and age band `k`, the metric reports:
- The indexer stores age-band spent output values internally as integer satoshis. The exporter converts each value to BTC and writes values with eight decimal places:
- This preserves the standard Bitcoin monetary precision.
- - verifies that all age-band values are present and parseable as decimals;
- External comparisons should be interpreted cautiously because providers may differ in timestamp convention, age-band boundaries, entity adjustment, change-output treatment, transfer-value definition, and historical edge-case handling.
- It can also be used to interpret threshold metrics. For example, the 365-day threshold metric should be closely related to the sum of age bands beginning at one year, provided that the band boundary and threshold convention match exactly.
- - uses fixed age-band boundaries;


---

## obm_spent_value_btc_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_spent_value_btc_daily` |
| Display name | Daily spent output value in BTC |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Exported from `obm_spent_output_indexer.sqlite` |
| External data required | No |
| Main use | Spent-output activity, denominator for dormancy, UTXO-flow analysis |

### Definicion
`obm_spent_value_btc_daily` measures the total BTC value of previous outputs consumed by non-coinbase transaction inputs in blocks assigned to a given UTC calendar day.

For each non-coinbase transaction input `i`, let:

```text
ValueBTC_i
```

be the BTC value of the previous output spent by that input.

Daily spent output value is obtained by summing these previous-output values over all non-coinbase inputs included in blocks assigned to UTC calendar day `d`:

```text
SpentValueBTC_d = sum_i ValueBTC_i
```

where the sum is taken over all spent outputs assigned to day `d`.

### Menciones de redondeo / frontera temporal
- The indexer stores spent output values internally as integer satoshis. The exporter converts this value to BTC and writes values with eight decimal places:
- This preserves the standard Bitcoin monetary precision.


---

## obm_spent_value_ge155d_btc_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_spent_value_ge155d_btc_daily` |
| Display name | 155-day CDD threshold spent value in BTC |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Exported from `obm_spent_output_indexer.sqlite` |
| External data required | No |
| Main use | Long-term-holder spent value, coin-age activity, UTXO-age analysis |

### Definicion
`obm_spent_value_ge155d_btc_daily` measures the BTC value of outputs spent on a given UTC calendar day whose age is at least 155 days.

For each spent output `i`, let:

```text
ValueBTC_i
```

be the BTC value of the previous output being spent, and let:

```text
AgeDays_i
```

be the age of that previous output, measured as the elapsed time in days between the block in which the output was created and the block in which it is spent.

The metric is defined as:

```text
CDD155BTC_d = sum_i ValueBTC_i * 1{AgeDays_i >= 155}
```

where the sum is taken over all spent outputs assigned to UTC calendar day `d`.

The unit is:

```text
BTC
```

This is important. Although the series belongs to the CDD family of coin-age metrics, it is not measured in BTC-days. It is a binary-threshold spent-value metric: each spent output either contributes its full BTC value if its age is at least 155 days, or contributes zero otherwise.

### Menciones de redondeo / frontera temporal
- `obm_spent_value_ge155d_btc_daily` and `obm_spent_value_ge365d_btc_daily` are parallel threshold spent-value metrics. They use the same logic but different age cutoffs:
- The indexer stores qualifying spent output values internally as integer satoshis. The exporter converts this value to BTC and writes values with eight decimal places:
- This preserves the standard Bitcoin monetary precision.


---

## obm_spent_value_ge365d_btc_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_spent_value_ge365_btc_daily` |
| Display name | 365-day CDD threshold spent value in BTC |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Exported from `obm_spent_output_indexer.sqlite` |
| External data required | No |
| Main use | Long-dormant spent value, coin-age activity, long-term-holder behavior |

### Definicion
`obm_spent_value_ge365_btc_daily` measures the BTC value of outputs spent on a given UTC calendar day whose age is at least 365 days.

For each spent output `i`, let:

```text
ValueBTC_i
```

be the BTC value of the previous output being spent, and let:

```text
AgeDays_i
```

be the age of that previous output, measured as the elapsed time in days between the block in which the output was created and the block in which it is spent.

The metric is defined as:

```text
CDD365BTC_d = sum_i ValueBTC_i * 1{AgeDays_i >= 365}
```

where the sum is taken over all spent outputs assigned to UTC calendar day `d`.

The unit is:

```text
BTC
```

This is important. Although the series belongs to the CDD family of coin-age metrics, it is not measured in BTC-days. It is a binary-threshold spent-value metric: each spent output either contributes its full BTC value if its age is at least 365 days, or contributes zero otherwise.

### Menciones de redondeo / frontera temporal
- The indexer stores qualifying spent output values internally as integer satoshis. The exporter converts this value to BTC and writes values with eight decimal places:
- This preserves the standard Bitcoin monetary precision.


---

## obm_spent_value_lt155d_btc_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_spent_value_lt155d_btc_daily` |
| Display name | Spent output value younger than 155 days in BTC |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Derived from existing OBM CSV files |
| External data required | No |
| Main use | Short-term spent value, UTXO-age decomposition, counterpart to >=155-day spent value |

### Definicion
`obm_spent_value_lt155d_btc_daily` measures the BTC value of outputs spent on a given UTC calendar day whose age is strictly less than 155 days.

The script computes the metric as a deterministic difference between two source series:

```text
SpentValueLT155dBTC_d =
    SpentValueBTC_d - SpentValueGE155dBTC_d
```

where `SpentValueBTC_d` is the total daily spent output value, corresponding to `obm_spent_value_btc_daily`, and `SpentValueGE155dBTC_d` is the daily spent output value for outputs aged at least 155 days, corresponding to `obm_spent_value_ge155d_btc_daily`.

Therefore:

```text
obm_spent_value_lt155d_btc_daily =
    obm_spent_value_btc_daily -
    obm_spent_value_ge155d_btc_daily
```

The threshold is strict on the output side: outputs aged less than 155 days are included, while outputs aged 155 days or more are excluded.

### Menciones de redondeo / frontera temporal
- - computing shares of spent value below and above the 155-day boundary;
- This relationship is exact when all series are generated from the same definitions, timestamp convention, and release version, apart from negligible decimal rounding effects.
- 11. allows tiny negative values only within the configured decimal tolerance and sets them to zero;
- Values below this absolute threshold are treated as rounding noise and set to zero.
- The script uses Python's `Decimal` type with high precision when subtracting BTC values. This reduces the risk of binary floating-point artifacts.
- - verifies that all source `value` fields are present and parseable as decimals;


---

## obm_supply_btc_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_supply_btc_daily` |
| Display name | Accumulated Bitcoin supply |
| Unit | `BTC` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Derived from `obm_issuance_btc_daily` |
| External data required | No |
| Main use | Period issuance, cumulative monetary flow, supply-growth analysis |

### Definicion
Let `Issuance_d` denote the realized Bitcoin issuance on UTC calendar day `d`, as reported by:

```text
obm_issuance_btc_daily
```

For a selected date interval from `s=2009-01-01` to `e`, both inclusive, accumulated supply at date `d` is defined as:

```text
AccumIssuance_d = sum_{k=s}^{d} Issuance_k
```

for every date `d` such that:

```text
s <= d <= e
```

The cumulative value is reset at 2009-01-01. Therefore, the value on the first date of the interval equals 
the daily issuance on that date:

```text
AccumIssuance_s = Issuance_s
```

This metric is therefore a cumulative Bitcoin supply since the Bitcoin genesis block.

### Menciones de redondeo / frontera temporal
- For a selected date interval from `s=2009-01-01` to `e`, both inclusive, accumulated supply at date `d` is defined as:
- `obm_supply_btc_daily` measures how much new Bitcoin has been issued cumulatively since the Bitcoin genesis block, inclusive.
- The script writes the `value` field with eight decimal places:
- This matches the BTC-denominated precision convention used by other OBM series.
- 5. filters the observations between the requested starting and ending dates, both inclusive;


---

## obm_tx_count_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_tx_count_daily` |
| Display name | Daily Bitcoin transaction count |
| Unit | `transactions` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Bitcoin Core full node |
| External data required | No |
| Main use | Network activity, transaction demand, settlement activity |

### Definicion
Let \(B_d\) denote the set of Bitcoin blocks assigned to UTC calendar day \(d\), and let \(N_b\) denote the number of transactions included in block \(b\). The daily transaction count is defined as:

```text
TxCount_d = sum_{b in B_d} N_b
```

A block is assigned to a day according to the UTC date derived from the block timestamp returned by Bitcoin Core.

Coinbase transactions are included because they are valid transactions contained in blocks and are part of the block-level transaction count.

### Menciones de redondeo / frontera temporal
- `obm_tx_count_daily` is a basic indicator of Bitcoin on-chain activity. It measures the number of confirmed transactions per UTC day.
- The script uses a safety height margin around the estimated date interval because Bitcoin block timestamps are not strictly monotonic in block height. This reduces the risk of missing blocks near daily boundaries.


---

## obm_utxo_eod_count_daily

### Resumen
| Field | Value |
|---|---|
| Series identifier | `obm_utxo_eod_count_daily` |
| Display name | End-of-day UTXO count |
| Unit | `outputs` |
| Frequency | `daily` |
| Time convention | UTC calendar day |
| Source layer | Direct Bitcoin Core block scan |
| External data required | No |
| Main use | UTXO set growth, scalability analysis, node-state burden, network-state diagnostics |

### Definicion
`obm_utxo_eod_count_daily` measures the number of spendable unspent transaction outputs after processing the highest-height block assigned to a given UTC calendar day.

Let `UTXOCountAfter_b` denote the number of spendable UTXOs after block `b` has been processed. Let `B_d` denote the set of blocks assigned to UTC date `d`. The metric is defined as:

```text
UTXOCountEOD_d =
    UTXOCountAfter_b*
```

where:

```text
b* = highest-height block in B_d
```

A block is assigned to a UTC calendar date using its block timestamp as returned by Bitcoin Core:

```text
d(b) = UTCDate(block_time_b)
```

If no block is assigned to date `d`, the value is undefined and is written as:

```text
NaN
```

This is because there is no end-of-day block under the selected UTC block-timestamp convention.

### Menciones de redondeo / frontera temporal
- 6. in checkpoint mode, locates the checkpoint boundary at the end of `--start_date`;
- The height-margin expansion is used because Bitcoin block timestamps are not strictly monotonic with respect to block height. The expanded scan interval reduces the risk of missing boundary blocks whose timestamps fall inside the selected ending date or checkpoint boundary.
