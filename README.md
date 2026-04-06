# Shoprenter URL ellenőrző GitHub Actionshöz

Ez a csomag arra való, hogy nagyobb URL-listát kulturált tempóban ellenőrizz:
- élő oldal-e,
- 404 / 410 hiba jön-e,
- van-e átirányítás,
- van-e átmeneti hiba vagy rate limit.

A script kifejezetten óvatos futásra van hangolva:
- egy szálon fut,
- random várakozást használ,
- retry-t használ 429 / 5xx hibákra,
- először `HEAD`-et próbál, és szükség esetén `GET`-re vált.

## A csomag tartalma

- `check_urls.py` – a Python script
- `requirements.txt` – szükséges csomagok
- `.github/workflows/check-urls.yml` – manuálisan indítható GitHub Actions workflow
- `input/` – ide tedd a bemeneti fájlt
- `output/` – ide készülnek az eredményfájlok futás közben

## Elvárt bemenet

A workflow alapból ezt a fájlt keresi:

`input/termekek.xlsx`

Ebben legyen egy `URL` nevű oszlop.

Ha más a fájlnév vagy az oszlopnév, a workflow indításakor meg tudod adni.

## GitHub használat – gyors lépések

1. Hozz létre egy új repót, vagy másold be a fájlokat egy meglévő repóba.
2. Tedd be a bemeneti fájlt az `input` mappába, például:
   - `input/termekek.xlsx`
3. Commit + push.
4. GitHubon nyisd meg az **Actions** fület.
5. Válaszd ki a **Shoprenter URL ellenorzes** workflow-t.
6. Kattints a **Run workflow** gombra.
7. Ha kell, módosítsd az inputokat:
   - `input_file`
   - `url_column`
   - `min_delay`
   - `max_delay`
   - `timeout`
   - `connect_timeout`
   - `save_every`
   - `use_head`
8. A futás végén az **Artifacts** részből letölthető az eredmény.

## Javasolt beállítások Shoprenterhez

Óvatos induló beállítás:
- `min_delay`: `1.5`
- `max_delay`: `2.5`
- `use_head`: `true`

Ha a HEAD kérés gyanúsan sok hamis hibát ad:
- `use_head`: `false`

## Kimeneti oszlopok

A script az eredeti adatok mellé ezeket írja ki:

- `Ellenorzott_URL`
- `Status_Code`
- `Vegso_URL`
- `Eredmeny`
- `Hiba`
- `Mod`

## Eredmény kategóriák

- `élő` – 2xx válasz
- `átirányítás` – 3xx válasz
- `404 / nem él` – 404 vagy 410
- `rate limited` – 429
- `kliens hiba` – egyéb 4xx
- `szerver hiba` – 5xx
- `hiba` – kérés közben kivétel történt

## Helyi futtatás opcionálisan

```bash
pip install -r requirements.txt
python check_urls.py --input input/termekek.xlsx --url-column URL
```

## Tipp

Ha az a cél, hogy kifejezetten a tényleges termékoldalakat szűrd ki, akkor utólag érdemes lehet ránézni a `Vegso_URL` oszlopra is. Előfordulhat, hogy egy régi termék-URL nem 404-et ad, hanem átirányítódik főoldalra vagy kategóriaoldalra.
