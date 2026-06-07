# MVQC Eğitim Sunucusu — Kurulum & Geliştirme Prompt'u

> Bu dosyayı **eğitim bilgisayarındaki (Ubuntu + NVIDIA RTX) Cursor'a prompt** olarak ver.
> Amaç: üretim istasyonunun (Raspberry Pi CM5) ürettiği veriyi alıp, **ROI başına EMPTY/FILLED
> sınıflandırıcıları** eğiten, ONNX'e çeviren ve istasyonun içe aktarabileceği **model bundle**
> üreten programı kurmak. Aşağıdaki kontratlar (klasör yapısı, `input_spec`, `manifest.json`,
> bundle ZIP düzeni) **birebir** korunmalı; aksi halde istasyon bundle'ı içe aktaramaz.

---

## 0. Cursor'a talimat (özet)

> "Aşağıdaki spesifikasyona göre `training-server/` adında bir Python projesi kur. Üretim
> istasyonundan USB ile gelen teaching örnekleri ve saha ROI arşivlerini bir 'data lake'e
> ingest et; ROI başına MobileNetV3-Small ile EMPTY/FILLED ikili sınıflandırıcı eğit; ONNX
> opset 17'ye çevir (parity kontrolü + opsiyonel INT8); kabul kapısını (FILLED recall ≥ 0.99,
> EMPTY recall ≥ 0.97) uygula; versiyonlu bir model registry'ye kaydet; ve istasyonun
> içe aktardığı `manifest.json + ONNX` bundle ZIP'ini üret. Tüm kontratlar bu dökümandaki
> gibi olmalı. CUDA destekli PyTorch wheel'i kur."

---

## 1. Sistem mimarisi

```
┌─────────────────────────┐         USB (şimdilik)          ┌──────────────────────────┐
│  ÜRETİM İSTASYONU        │   günlük export ZIP  ───────►   │  EĞİTİM SUNUCUSU          │
│  Raspberry Pi CM5        │                                 │  Ubuntu + RTX GPU         │
│  - kamera + barkod       │                                 │  - ingest → data lake     │
│  - ROI teaching          │   ◄───────  model bundle ZIP    │  - train (GPU)            │
│  - ONNX inference        │            (USB ile geri)       │  - ONNX export + registry │
│  - SADECE çalıştırır     │                                 │  - bundle üretir          │
│  ASLA eğitim yapmaz      │                                 │  TÜM EĞİTİM BURADA        │
└─────────────────────────┘                                 └──────────────────────────┘
```

- **İstasyon eğitim yapmaz.** Sadece teaching örnekleri toplar, model çalıştırır, veri arşivler.
- **Eğitim sunucusu** tüm GPU işini yapar, ONNX bundle üretir.
- Aktarım **şu an USB** ile; ileride ağ (`NetworkSyncClient`) eklenebilir, aynı kontratla.

---

## 2. Problem tanımı (V1: Bileşen Varlığı)

- Her **ürün (product)** bir veya birden çok **yüzey (surface)** içerir.
- Her yüzeyde operatörün çizdiği **ROI (Region of Interest)** dikdörtgenleri vardır.
- Her ROI için **iki sınıf**: `EMPTY` (parça yok) ve `FILLED` (parça var).
- **ROI başına ayrı bir ikili sınıflandırıcı** eğitilir. (Tüm ROI'ler için tek model DEĞİL.)
- Sınıf listesi her yerde sabittir: `CLASSES = ["EMPTY", "FILLED"]` (sıra önemli; index 0=EMPTY, 1=FILLED).

---

## 3. İstasyonun ürettiği veri (giriş kontratı)

İstasyon, seçili depolama biriminin (USB/NVMe/SSD) kök dizinine şu yapıyı yazar:

```
<storage_root>/
├── teaching/                       # operatörün etiketlediği öğretme örnekleri
│   └── <ÜrünAdı>/
│       └── surface_<i>/
│           ├── EMPTY/
│           │   └── roi_<idx>/
│           │       ├── 20260607_153000_000_000.jpg
│           │       └── ...         (~20 kare)
│           └── FILLED/
│               └── roi_<idx>/
│                   └── ...
├── full_images/                    # tam kare görüntüler (FAIL + örnek PASS)
│   └── YYYY-MM-DD/
│       └── YYYYMMDD_HHMMSS_<Ürün>_<PASS|FAIL>.jpg
├── roi_archive/                    # saha denetim sonuçları (ROI kırpıntıları + metadata)
│   └── inspection_000123/
│       ├── roi_1.jpg
│       ├── roi_2.jpg
│       └── metadata.json
└── exports/                        # günlük paketlenmiş ZIP'ler (aktarım birimi)
    └── YYYY-MM-DD.zip
```

### 3.1. Teaching örnekleri (ana eğitim kaynağı)

- **Etiket klasör adından gelir:** `EMPTY` veya `FILLED`. Operatör Teaching ekranında
  "Capture EMPTY" / "Capture FILLED" butonuna basar; o oturumun tüm kareleri o etikettir.
- Görüntüler **ROI kırpıntısıdır** (tam kare değil), **BGR** renk, **JPEG** (quality ~85).
- Çekim sırasında exposure/gain varsayılan olarak sabittir (gerçek ışık koşuluna yakın).
  İstasyonda `condition_sweep` açıksa dar aralıkta exposure/gain çeşitlendirmesi olur.

### 3.2. Günlük export ZIP (aktarım birimi)

İstasyon her gün `exports/YYYY-MM-DD.zip` üretir. İçeriği:

```
full_images/<dosya>.jpg
roi_archive/inspection_000123/{roi_*.jpg, metadata.json}
metadata/inspection_000123.json     (kolaylık için düz kopya)
```

> Not: Teaching örnekleri günlük ZIP'e dahil **olmayabilir**; teaching klasörü ayrıca
> kopyalanır. İngest hem ham `teaching/` dizinini hem de export ZIP'ini kabul etmeli.

### 3.3. `metadata.json` şeması (saha ROI arşivi etiketleri)

Saha denetim sonuçları buradan etiketlenir. Şema (Pydantic, istasyonla birebir):

```json
{
  "inspection_id": "string",
  "product": "Product_A",
  "barcode": "8691234567890",
  "surface": 1,
  "timestamp": "2026-06-07T15:30:00",
  "result": "PASS",
  "confidence": 0.97,
  "saved_reason": "low_confidence | fail | random_sample",
  "recipe_version": 1,
  "station_id": "cm5-101",
  "roi_results": { "roi1": "FILLED", "roi2": "EMPTY" },
  "roi_detail": [
    { "name": "roi1", "label": "FILLED", "confidence": 0.98,
      "decision": "OK", "model_version": "2026.06.07-153000" }
  ]
}
```

- Saha etiketi **`roi_results`** map'inden alınır: `{"roi1": "FILLED", ...}`.
- `roi_archive/inspection_xxx/roi_<idx>.jpg` dosyası `roi_results["roi<idx>"]` ile eşlenir.

---

## 4. Veri aktarımı (istasyon → eğitim sunucusu)

**Şu anki yöntem: USB.**

1. İstasyonda seçili depolama biriminden `exports/*.zip` ve `teaching/` klasörünü USB'ye kopyala.
2. USB'yi eğitim sunucusuna tak.
3. `ingest` adımıyla data lake'e aktar.

> İleride: ağ üzerinden pull/push. Kontrat aynı kalır (ZIP + manifest tabanlı), sadece
> taşıma katmanı değişir. Şimdilik USB için yaz, ama ingest fonksiyonunu taşımadan bağımsız tut.

---

## 5. Data lake (ingest çıktısı)

İngest, kaynak ne olursa olsun (ham `teaching/`, export ZIP veya çıkarılmış dizin) içeriği
**içerik hash'i ile tekilleştirerek (dedup)** şu kanonik düzene kopyalar:

```
data/lake/<ÜrünAdı>/surface_<i>/roi_<idx>/<EMPTY|FILLED>/<sha256>.jpg
```

- **Teaching kaynağı:** `teaching/<Product>/surface_<i>/<LABEL>/roi_<idx>/*.jpg`
  → `lake/<Product>/surface_<i>/roi_<idx>/<LABEL>/<sha>.jpg`
- **Saha kaynağı:** `roi_archive/inspection_xxx/metadata.json` → her `roi_results` girdisi
  ilgili `roi_<idx>.jpg` ile eşlenip `lake/.../<LABEL>/<sha>.jpg` olur.
- Aynı içerikli (aynı sha256) dosya tekrar ingest edilmez → tekrar tekrar çalıştırılabilir (idempotent).

---

## 6. KRİTİK ortak kontrat: `input_spec` (ön-işleme)

İstasyon ve eğitim sunucusu **birebir aynı** ön-işlemeyi kullanmalı. V1 varsayılanı:

```python
DEFAULT_INPUT_SPEC = {
    "layout": "NCHW",                       # veya NHWC
    "size":   [224, 224],                   # (w, h)
    "color":  "RGB",                        # veya BGR / GRAY
    "mean":   [0.485, 0.456, 0.406],
    "std":    [0.229, 0.224, 0.225],
    "scale":  0.00392156862745098,          # 1/255, mean/std'den ÖNCE uygulanır
}
CLASSES = ["EMPTY", "FILLED"]               # index 0=EMPTY, 1=FILLED
```

Ön-işleme sırası: **resize → renk dönüşümü (BGR→RGB) → `*scale` → `(x-mean)/std` → layout (HWC→CHW) → batch ekle.**
Bu `input_spec`, eğitilen modelin `card.json` ve bundle `manifest.json` içine **aynen yazılır**;
istasyon bunu okuyup aynı ön-işlemeyi uygular.

---

## 7. Proje yapısı (eğitim sunucusunda oluşturulacak)

```
training-server/
├── common.py                  # CLASSES, input_spec, sha256, Manifest/ModelEntry dataclass
├── requirements.txt           # torch(+CUDA), torchvision, onnx, onnxruntime, numpy, pillow
├── ingest/ingest.py           # teaching + ROI arşivi → data lake (dedup)
├── datasets/build_dataset.py  # ROI başına stratified train/val/test split (JSON)
├── training/train_roi.py      # MobileNetV3-Small eğitimi (GPU) + metrics
├── export/export_onnx.py      # ONNX opset 17 + parity check + opsiyonel INT8
├── export/make_dummy_model.py # gerçek eğitimden önce brightness-threshold placeholder ONNX
├── registry/registry.py       # versiyonlu registry + kabul kapısı + model card
├── deploy/build_bundle.py     # registry'den ürün için bundle ZIP üretir
└── pipelines/monthly_retrain.py  # uçtan uca orkestrasyon (subprocess zinciri)
```

---

## 8. Her adımın davranışı (birebir spesifikasyon)

### 8.1. `common.py`
- `CLASSES = ["EMPTY", "FILLED"]`, `INPUT_SIZE = 224`.
- `input_spec(size=224)` → yukarıdaki `DEFAULT_INPUT_SPEC` (size override edilebilir).
- `sha256_file(path)` → 64KB chunk'larla SHA-256.
- `@dataclass ModelEntry`: `surface_index, roi_index, roi_name, version, onnx_file, classes,
  input_spec, checksum_sha256, metrics, training_run_id`.
- `@dataclass Manifest`: `product_name, product_barcode, recipe_version, bundle_version="1.0",
  created_at, source="manual_usb", models: List[ModelEntry]`, `to_json()` → indent=2.
- **Bağımlılık-hafif** olmalı (numpy/onnx); torch sadece training/export'ta import edilir.

### 8.2. `ingest/ingest.py`
- Girdi: `--src` (export ZIP, dizin veya ham SSD kökü), `--lake` (hedef data lake).
- ZIP ise geçici dizine çıkar; `teaching/` varsa onu, yoksa kökü teaching kaynağı say.
- `ingest_teaching`: 5+ parça yol `<Product>/surface_<i>/<LABEL>/roi_<idx>/*.jpg`'yi dedup kopyala.
- `ingest_roi_archive`: her `metadata.json` için `roi_results` map'inden etiketle.
- Çıktı JSON: `{"ingested_teaching": N, "ingested_field": M, "lake": "..."}`.

### 8.3. `datasets/build_dataset.py`
- Girdi: `--roi-dir data/lake/<Product>/surface_<i>/roi_<idx>`, `--out <split>.json`.
- Her sınıf (`EMPTY`, `FILLED`) için dosyaları topla, **stratified** train/val/test böl
  (varsayılan val=0.15, test=0.15, seed=42).
- Çıktı JSON: `{"classes", "roi_dir", "train":[{path,label}], "val":[...], "test":[...], "counts":{...}}`.

### 8.4. `training/train_roi.py`
- Girdi: `--split <split>.json`, `--out <model_dir>`, `--epochs 15`, `--batch 32`, `--lr 3e-4`, `--run-id`.
- Model: `torchvision.mobilenet_v3_small(weights=DEFAULT)`, son linear → `len(CLASSES)` çıkış.
- Augmentation (train): brightness ×[0.6,1.5], gamma [0.7,1.4], gaussian noise, horizontal flip.
  (Üretim için Albumentations'a geçilebilir.)
- Ön-işleme `input_spec` ile (scale → mean/std → CHW). Cihaz: `cuda` varsa GPU.
- En iyi val accuracy checkpoint'i kaydet: `model.pt` = `{state_dict, classes, arch, input_spec}`.
- Test metriklerini yaz: `metrics.json` = `{run_id, best_val_accuracy, test:{accuracy, recall:{EMPTY,FILLED}, n}, counts}`.
- `recall` sınıf bazında hesaplanır (kabul kapısı bunu kullanır).

### 8.5. `export/export_onnx.py`
- Girdi: `--ckpt model.pt`, `--out model.onnx`, `--quantize` (opsiyonel).
- `torch.onnx.export` **opset 17**, `input_names=["input"]`, `output_names=["output"]`,
  `dynamic_axes={"input":{0:"batch"}, "output":{0:"batch"}}`.
- **Parity check**: torch çıktısı ile onnxruntime çıktısı arası `max_abs_diff`; >1e-3 ise uyar.
- `--quantize` → `quantize_dynamic` ile `model.int8.onnx` (QInt8).
- Çıktı JSON: `{onnx, classes, input_spec, opset, parity_max_abs_diff, checksum_sha256, quantized}`.

### 8.6. `registry/registry.py`
- **Kabul kapısı (GATE):** `FILLED_recall ≥ 0.99`, `EMPTY_recall ≥ 0.97` (test split üzerinde).
  Geçmezse `--force` olmadan **reddet**.
- Layout: `registry/<Product>/surface_<i>/roi_<idx>/<version>/{model.onnx, card.json}`
  + `latest` pointer dosyası (içinde version yazar).
- `version = datetime "%Y.%m.%d-%H%M%S"`.
- `card.json`: `{product, surface_index, roi_index, roi_name, version, classes, input_spec,
  metrics, training_run_id, checksum_sha256, gate, created_at}`.

### 8.7. `deploy/build_bundle.py` — **istasyonun içe aktardığı çıktı**
- Girdi: `--registry`, `--product`, `--barcode`, `--recipe-version`, `--out <bundle>.zip`.
- Ürünün her (surface, roi) için **latest** registered modeli bul.
- **Bundle ZIP düzeni:**
  ```
  manifest.json
  models/surface_<i>_roi_<idx>.onnx
  ```
- `manifest.json` = `Manifest.to_json()`; her `ModelEntry` `onnx_file` alanı ZIP içindeki
  yola (`models/surface_<i>_roi_<idx>.onnx`) işaret eder, `checksum_sha256` ONNX'in hash'idir.
- İstasyon bu ZIP'i alır, manifest'i doğrular, **her ONNX'in SHA-256'sını manifest'le karşılaştırır**,
  ROI'lere (aktif recipe'deki `surface_index`+`roi_index`) eşler, atomik olarak aktive eder,
  registry'yi hot-reload eder ve ürün tam kapsandıysa `ready` yapar.

### 8.8. `pipelines/monthly_retrain.py`
- Data lake'te ürünün ROI'lerini keşfet; her ROI için sırayla (subprocess):
  `build_dataset → train_roi → export_onnx → registry.register`.
- Sonra `build_bundle` ile `<Product>_<YYYY-MM-DD>.zip` üret.
- Argümanlar: `--lake --product --barcode --recipe-version --workdir --registry --out --epochs --force-register`.

### 8.9. `export/make_dummy_model.py` (placeholder)
- Gerçek eğitim verisi yokken: ROI ortalama (ön-işlenmiş) parlaklığı 0.5'i geçerse `FILLED`,
  yoksa `EMPTY` veren brightness-threshold bir ONNX üret. Tüm deploy/inference yolunu
  GPU modeli olmadan smoke-test etmeye yarar.

---

## 9. Kurulum

```bash
cd training-server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # GPU'na uygun CUDA PyTorch wheel'ini kur
```

`requirements.txt` (minimum): `torch`, `torchvision` (CUDA wheel), `onnx`, `onnxruntime`,
`numpy`, `pillow`. (İstersen `albumentations`, `scikit-learn`.)

---

## 10. Uçtan uca komutlar (örnek: Product_A)

```bash
# 1) İstasyon export'unu / teaching klasörünü lake'e ingest et
python ingest/ingest.py --src /media/<user>/USB/2026-08-01.zip --lake data/lake
python ingest/ingest.py --src /media/<user>/USB/teaching        --lake data/lake

# 2) Tek komutla aylık yeniden eğitim + bundle
python pipelines/monthly_retrain.py --lake data/lake --product Product_A \
    --barcode 8691234567890 --recipe-version 1 \
    --registry registry --out data/bundles --epochs 15

# Çıktı: data/bundles/Product_A_2026-08-01.zip  → bu ZIP'i USB ile istasyona götür
```

İstasyonda içe aktarma: **Models** sekmesi → bundle ZIP'i seç → import; ya da CLI:
```bash
python -m station.cli import-model --bundle /media/usb/Product_A_2026-08-01.zip
```

---

## 11. Kabul kriterleri / sağlama

- [ ] `CLASSES` her yerde `["EMPTY", "FILLED"]`, sıra değişmez.
- [ ] `input_spec` istasyondaki ile **bit bit** aynı (size, mean, std, scale, layout, color).
- [ ] ONNX **opset 17**, giriş adı `input`, çıkış adı `output`, dinamik batch ekseni.
- [ ] Parity diff < 1e-3.
- [ ] Kabul kapısı: FILLED recall ≥ 0.99, EMPTY recall ≥ 0.97.
- [ ] Bundle ZIP: kökte `manifest.json` + `models/surface_<i>_roi_<idx>.onnx`.
- [ ] Manifest'teki her `checksum_sha256`, ZIP içindeki ONNX'in gerçek SHA-256'sı.
- [ ] `manifest.product_name` (ve/veya `product_barcode`) istasyondaki ürünle eşleşir.
- [ ] `surface_index` ve `roi_index` istasyon recipe'sindeki değerlerle birebir aynı.
- [ ] İngest idempotent (aynı sha tekrar kopyalanmaz).
- [ ] Placeholder model ile tüm yol GPU'suz smoke-test edilebilir.

---

## 12. Sık hatalar

- **Bundle import "unknown product":** `manifest.product_name` istasyondaki ürün adıyla
  (veya barkodla) eşleşmiyor.
- **Bundle import "no matching ROI":** `surface_index`/`roi_index` istasyonun aktif
  recipe'siyle uyuşmuyor — istasyonda ROI'ler aynı index'lerle tanımlı olmalı.
- **Checksum mismatch:** ONNX, manifest yazıldıktan sonra değişmiş; bundle'ı yeniden üret.
- **Yanlış tahminler / düşük güven:** `input_spec` uyuşmazlığı (en sık: scale veya color
  BGR/RGB karışması). İstasyon ile aynı olduğunu doğrula.
- **Az veri:** ROI başına EMPTY ve FILLED için yeterli ve dengeli örnek toplandığından emin ol.
```
