# 10-minute demo walkthrough

A script for showing this project live. Every e-mail, sender and file in the demo is synthetic.

## Order of the demo

| Time | Show | Say |
| --- | --- | --- |
| 0:00–1:00 | README, first table | The problem: country files arrive by e-mail and someone has to file them by hand. The first version of this tool misfiled 8 of 17 files. |
| 1:00–3:00 | `python organise.py --demo` in the terminal | 14 messages scanned, 16 files saved, 1 duplicate, 1 signature logo skipped, 1 message not sent to the data address. Each line shows the country, the type and the file. |
| 3:00–5:00 | The HTML report under `output/ESA/_reports/` | The counts by country and type, then the **reason** column. Point to the three cases below. |
| 5:00–7:00 | `organiser/classify.py`, `decide()` | The weights, the file-name rule and the two review rules: about 30 lines. |
| 7:00–8:00 | `output/ESA/_manifest.csv` | One line per attachment with the SHA-256: this is the audit trail. |
| 8:00–9:00 | `pytest -q` (36 passed), the green CI badge | Each demo situation is a test, including the false matches (`Measles` ≠ LES). |
| 9:00–10:00 | `config.yaml` | Countries, codes, domains, weights and thresholds live here, so a new team changes no code. |

## The three real misfiling cases

The first version (`organiser/legacy.py`) joined the subject, body, sender and file names into one text and took the **longest country name found anywhere**. It never read file codes and never removed quoted threads.

1. **Eritrea filed as Ethiopia.** `ERI EPI Monthly data…xls` and `EriAFP_2026_03.zip` were sent by the Ethiopia country office. The signature says *Ethiopia*, and the codes `ERI` / `Eri` were never read (Eritrea was not even in the first version's country list). **Now:** the file name decides → Eritrea / RI and Eritrea / AFP.
2. **Malawi filed as Mozambique.** `AFP_MAL_2026 database….zip` is a reply. The quoted regional thread below it says "Mozambique, Malawi: please send…". "Mozambique" is the longer name, so it won. **Now:** the code `MAL` in the file name decides, and quoted text (`From:`, `Sent:`, `>` lines, `On … wrote:`, French `De :` / `Le … a écrit`) is cut before the body is read at all.
3. **Lesotho filed as Malawi.** `MLABLES_Forward (85).zip` was forwarded by a Malawi lab focal point, so the sender and body said Malawi. **Now:** `MLAB` + `LES` is read as a Lesotho lab file.

These three cases share one lesson: **the person who sends a file is often not the country the file belongs to.** The file name is what the country itself wrote, so it is the strongest evidence.

## Evidence weights and the review rule

| Evidence | Weight |
| --- | :---: |
| File name: country code (with prefixes such as `A`, `M`, `AFP`, `MLAB`, `MREG`) or name | 5 |
| Subject | 3 |
| Sender's e-mail domain | 2 |
| Body, after quoted threads are removed | 1 |

- **If the file name names exactly one country, that decides** (confidence *high*).
- Otherwise each source adds its weight once per country. The file goes to **`_Needs_Review`** when:
  - the best score is **below 2**: one mention in the body only (demo: "Zimbabwe" in the body → review);
  - the runner-up has **≥ 75%** of the best score (demo: the subject names Namibia *and* Botswana, 3 vs 3 → review).
- Example of a *medium* decision: Botswana KPIs, where the sender domain (2) + the signature (1) = 3 and no other country scores.
- Codes must fill a whole token, so `Measles` is not Lesotho, `Malaria` is not Malawi and `Communication` is not Comoros. Each of these has a test.

## De-duplication by SHA-256

Every saved file's bytes are hashed with SHA-256, and the hash is stored in `_manifest.csv`. On the next attachment (or the next run), a known hash is logged as *duplicate* with the path of the first copy, and nothing is written. This is based on **content, not the name**: a re-sent `Indicators…KPIs.xlsx` is caught, while two different files with the same name are both kept (`_1`, `_2`).

## Why the demo uses .eml files

- Anyone can run it: no Outlook, no Windows, no mailbox. CI runs it on Linux on every push.
- No real data or addresses leave the organisation. The demo writes synthetic `.eml` files into `inbox_demo/`.
- `.eml` is what Outlook exports, so the same reader also works on real mail saved to a folder (`--source eml --eml-dir …`).

## Running on Outlook: dry run first

```powershell
.venv\Scripts\Activate.ps1
$env:TARGET_RECIPIENTS = "ri.data@example.org,epi.data@example.org"   # use the real addresses; never committed
$env:ESA_ROOT = "C:\Data\ESA"
python organise.py --source outlook --dry-run --days 7      # decides and reports, saves nothing
# read the report: are the countries right? what went to review?
python organise.py --source outlook --days 30               # then save for real
python organise.py --source outlook --outlook-folder "Inbox/RI data"
```

`--dry-run` still writes the HTML report, so each decision can be checked against the real mailbox before any file is moved.

## Likely questions

- **Why not machine learning?** There are about 20 countries, the codes are fixed, and every decision must be explainable to a data manager. Rules with written reasons are auditable, and the configuration is the training data.
- **What happens when it's wrong?** The reason in the manifest shows which evidence decided. Fix the code or the alias in `config.yaml` and add a test case.
- **Why not just ask senders to name files properly?** They mostly do. The codes (`AUGA`, `MLABMAL`) are the convention, and the tool reads that convention instead of ignoring it.
- **A new country or code?** Add one line to `config.yaml`. No code changes are needed.
- **Re-running on the same mail?** Every file is recorded as a duplicate and nothing is saved twice.
- **Zip files?** They are extracted next to the archive, and any member path that would land outside the folder (`../`) is refused.
- **Signature logos?** Inline images, and images under 100 KB, are skipped and logged.
- **Security?** Real recipient addresses and paths come from environment variables and are never committed. The repo contains only `*.example` addresses.
- **What would you add next?** A small review step that asks someone to confirm `_Needs_Review` files and writes the answer back as a new alias, plus a scheduled task for a daily run.
