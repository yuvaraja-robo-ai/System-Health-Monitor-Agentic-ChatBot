# Thermal throttling / overheating

tags: temp, thermal, jetson

SoC or package temp > 85°C triggers throttling and degrades performance.

## Steps

1. Check `soc.temp` and fan percentage.
2. Verify airflow / heatsink contact / enclosure.
3. On Jetson: consider lower power mode (`nvpmodel -m 1` = 15W).
4. Reduce GPU workload if applicable.
