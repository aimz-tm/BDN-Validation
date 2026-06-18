# Sample BDN files

Place your sample bunker delivery note images here (PNG, JPEG, or PDF).

They are used to:

1. **Calibrate** quantity/duration priors: `python scripts/calibrate_from_bdns.py`
2. **Test** OCR and validation via the dashboard

They do **not** train the Isolation Forest. AIS ML training uses **synthetic** bunkering patterns:

```bash
python scripts/train_model.py
```
