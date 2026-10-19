# Transcript

## Prompt

`validation_runs.csv` is an export of our nightly `cvt-regression` results for May and
June: one row per test case per nightly batch. A case passes when its `max_abs_error`
against the reference filter is below 1e-7. The nightly has been going red a lot more
than it used to, and so far all I've heard are theories, from flaky tests to one of the
worker machines. Nobody has actually gone through the numbers.

Could you dig into it and tell me what is really going on: when it started, what it
lines up with, how big the effect is, and which explanations the data rules out? Write
it up in `analysis.md`, with at least one plot (PNG) I can drop into the team update.

Please also put the key numbers in `findings.json` so I can paste them into the
tracker:

```json
{
  "regression_start_date": "YYYY-MM-DD, the first nightly batch affected",
  "explained_by": "the column that explains it: one of version, worker, test_id, none",
  "culprit": "the value of that column responsible",
  "baseline": "the value of that column you compare the culprit against",
  "magnitude_factor": 0.0,
  "affected_workers": ["worker names"],
  "per_version": {
    "vX.Y.Z": {"runs": 0, "mean_max_abs_error": 0.0, "median_max_abs_error": 0.0, "fail_rate": 0.0}
  }
}
```

`magnitude_factor` is the median `max_abs_error` for `culprit` divided by the median
for `baseline`. `per_version` covers every version in the file, over all of its rows;
`fail_rate` is the fraction (0 to 1) of cases at or above 1e-7.


- `$ Get-ChildItem; Get-Content validation_runs.csv -TotalCount 8; (Get-Content validation_runs.csv | Measure-Object -Line).Lines; python --version`
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-csv-analysis-b_41j2mz/working" && python -c "
  import pandas as pd
  d=pd.read_csv('validation_runs.csv')
  print(d.dtypes); print(d.isna().sum()); print(d.describe(include='all').T)
  for c in ['batch','run_date','worker','version','n_vectors']: print(d[c].value_counts().sort_index().to_string()[:3000])
  print(d.duplicated().sum(), d.duplicated(['batch','test_id']).sum())
  "
  ```

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-csv-analysis-b_41j2mz/working" && python -c "
  import pandas as pd
  pd.set_option('display.width',250); pd.set_option('display.max_rows',200)
  d=pd.read_csv('validation_runs.csv'); d['fail']=d.max_abs_error>=1e-7
  g=d.groupby('run_date').agg(vers=('version',lambda s:','.join(sorted(s.unique()))),w1=('worker',lambda s:(s=='estimator-01').sum()),med=('max_abs_error','median'),mx=('max_abs_error','max'),fails=('fail','sum'),rt=('runtime_ms','median'))
  print(g.to_string())
  print(d.groupby(['version','worker']).agg(n=('fail','size'),med=('max_abs_error','median'),fr=('fail','mean'),rt=('runtime_ms','median')))
  "
  ```

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-csv-analysis-b_41j2mz/working" && python -c "
  import pandas as pd, numpy as np
  pd.set_option('display.width',250); pd.set_option('display.max_rows',200)
  d=pd.read_csv('validation_runs.csv'); d['fail']=d.max_abs_error>=1e-7
  print(d[(d.version=='v2.2.0')&d.fail])
  print(d.groupby('test_id').worker.nunique().value_counts())
  post=d[d.version!='v2.2.0']; pre=d[d.version=='v2.2.0']
  t=post.groupby('test_id').agg(fr=('fail','mean'),med=('max_abs_error','median'))
  print(t.describe()); print((t.fr==0).sum(),'tests never fail post')
  print(t.sort_values('fr').head(5)); print(t.sort_values('fr').tail(5))
  # per-test persistence: correlate log error across halves
  post=post.assign(le=np.log10(post.max_abs_error))
  a=post[post.run_date<'2026-06-15'].groupby('test_id').le.mean(); b=post[post.run_date>='2026-06-15'].groupby('test_id').le.mean()
  print('per-test corr halves',a.corr(b))
  print('log10 err pre: mean %.2f sd %.2f; post mean %.2f sd %.2f'%(np.log10(pre.max_abs_error).mean(),np.log10(pre.max_abs_error).std(),post.le.mean(),post.le.std()))
  print('min post err',post.max_abs_error.min(),'max pre (excl outlier)',pre.max_abs_error.nlargest(3).tolist())
  from scipy import stats
  print(stats.mannwhitneyu(d[d.version=='v2.3.0'].max_abs_error,d[d.version=='v2.3.1'].max_abs_error))
  for v in ['v2.3.0','v2.3.1']:
    s=d[d.version==v]; print(v, stats.mannwhitneyu(s[s.worker=='estimator-01'].max_abs_error,s[s.worker=='estimator-02'].max_abs_error).pvalue)
  print(stats.mannwhitneyu(d[d.run_date.between('2026-05-24','2026-05-30')].runtime_ms,d[d.run_date.between('2026-05-31','2026-06-06')].runtime_ms).pvalue)
  print(d.groupby('worker').runtime_ms.describe())
  # daily fail count distribution
  print(post.groupby('run_date').fail.sum().describe())
  "
  ```

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-csv-analysis-b_41j2mz/working" && python -c "
  import pandas as pd, numpy as np
  from scipy import stats
  d=pd.read_csv('validation_runs.csv'); d['fail']=d.max_abs_error>=1e-7; d['lg']=np.log10(d.max_abs_error)
  post=d[d.version!='v2.2.0']; pre=d[d.version=='v2.2.0']
  print(pre[pre.test_id==1838].max_abs_error.describe())
  print('log10 pre mean %.2f sd %.2f; post mean %.2f sd %.2f'%(pre.lg.mean(),pre.lg.std(),post.lg.mean(),post.lg.std()))
  print('min post',post.max_abs_error.min(),'pre top3',pre.max_abs_error.nlargest(3).tolist())
  print('2.3.0 vs 2.3.1',stats.mannwhitneyu(d[d.version=='v2.3.0'].max_abs_error,d[d.version=='v2.3.1'].max_abs_error).pvalue)
  for v in d.version.unique():
    s=d[d.version==v]; print(v,'worker MWU p',stats.mannwhitneyu(s[s.worker=='estimator-01'].max_abs_error,s[s.worker=='estimator-02'].max_abs_error).pvalue)
  print('runtime wk before/after p',stats.mannwhitneyu(d[d.run_date.between('2026-05-24','2026-05-30')].runtime_ms,d[d.run_date.between('2026-05-31','2026-06-06')].runtime_ms).pvalue)
  print(d.groupby(['worker','version']).runtime_ms.median())
  # fail rate binomial dispersion per test: chi2
  ct=pd.crosstab(post.test_id,post.fail); print('test-vs-fail chi2 p',stats.chi2_contingency(ct)[1])
  print(post.groupby('run_date').fail.sum().describe())
  for v in d.version.unique():
    s=d[d.version==v].max_abs_error; print(v,len(s),s.mean(),s.median(),(s>=1e-7).mean())
  print(d[d.version=='v2.3.0'].max_abs_error.median()/pre.max_abs_error.median())
  print('new tests appear?', set(post.test_id)-set(pre.test_id))
  "
  ```

The cause is clear: the error jumped about 170× on the first v2.3.0 nightly. Workers and individual tests don't explain it. Next I'm making the plot, then the write-up.

- `tool` Skill
- `$ cd "G:/Willikers/sandbox/demoforge-csv-analysis-b_41j2mz/tmp/claude/bundled-skills/2.1.289/eb374f894294050f389ac4a763531288/dataviz" && grep -n -i -A3 "categorical\|surface\|ink\|text" references/palette.md | head -80`
- `$ cd "G:/Willikers/sandbox/demoforge-csv-analysis-b_41j2mz/tmp/claude/bundled-skills/2.1.289/eb374f894294050f389ac4a763531288/dataviz" && sed -n 52,64p references/palette.md && node scripts/validate_palette.js "#2a78d6,#eb6834" --mode light 2>&1 | tail -15`
- `file_write` G:\Willikers\sandbox\demoforge-csv-analysis-b_41j2mz\working\analyze.py
- `$ cd "G:/Willikers/sandbox/demoforge-csv-analysis-b_41j2mz/working" && python analyze.py`
- `file_read` G:\Willikers\sandbox\demoforge-csv-analysis-b_41j2mz\working\regression_timeline.png
Fixing a label that overlaps the legend, and marking the missing Jun 14 batch.

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-csv-analysis-b_41j2mz/working" && python - <<'EOF'
  p='analyze.py'; s=open(p).read()
  s=s.replace('ax1.text(daily.index[0], THRESHOLD * 1.25, "pass threshold 1e-7", color=INK2, fontsize=9)',
   'ax1.text(pd.Timestamp("2026-05-29"), THRESHOLD * 1.25, "pass threshold 1e-7", color=INK2, fontsize=9, ha="right")')
  s=s.replace('bbox_to_anchor=(0, 0.93)','bbox_to_anchor=(0, 0.62)')
  s=s.replace('ax2.set_ylabel("failing cases\\n(of 51)")',
   'ax2.set_ylabel("failing cases\\n(of 51)")\nax2.text(pd.Timestamp("2026-06-14"), 0.5, "no\\nbatch", ha="center", va="bottom", fontsize=8, color=INK2)')
  open(p,'w').write(s)
  EOF
  python analyze.py >/dev/null && echo ok
  ```

- `file_read` G:\Willikers\sandbox\demoforge-csv-analysis-b_41j2mz\working\regression_timeline.png
- `search` no\\nbatch|failing cases
- `file_edit` G:\Willikers\sandbox\demoforge-csv-analysis-b_41j2mz\working\analyze.py
- `$ cd "G:/Willikers/sandbox/demoforge-csv-analysis-b_41j2mz/working" && python analyze.py >/dev/null && echo ok`
- `file_read` G:\Willikers\sandbox\demoforge-csv-analysis-b_41j2mz\working\regression_timeline.png
- `file_write` G:\Willikers\sandbox\demoforge-csv-analysis-b_41j2mz\working\analysis.md
The nightly started going red with the **2026-05-31** batch, the first one run on **v2.3.0**. That night `max_abs_error` jumped about **172×** on the median, from 2.96e-10 to 5.09e-8. It hit every test and both workers, and it hasn't come back down. **v2.3.1**, which took over on 06-10, didn't fix it: its error is statistically the same as v2.3.0's.

**Why it looks flaky:** the errors now sit about 2× below the 1e-7 threshold. Normal run-to-run noise pushes a random ~20% of cases over the line each night, so you see between 6 and 17 failures out of 51. That spread is about what you'd expect if each case independently had a ~21% chance of failing.

**Explanations the data rules out:**
- **A bad worker.** Both workers jumped together on the same night, with the same error and fail rates before and after. `estimator-02` is consistently slower (55.8 ms vs 47.6 ms), which may be why people suspected it, but that gap was there before the change and doesn't affect accuracy.
- **Flaky tests.** All 51 tests failed at least once after the change. Failures don't cluster on particular tests (p = 0.68), and a test's error in one half of the period barely predicts the other half.
- **Drift or changed inputs.** v2.2.0 is flat for 30 nights, then there's a single step. `n_vectors` and the test set never change. The lowest error after the change is still 4.5× higher than the worst normal v2.2.0 result.
- **The one v2.2.0 failure** (05-14, test 1838) is an unrelated one-off.

**The one thing the data can't separate:** v2.3.0 went out on the same night the errors jumped. If something else in CI also changed on 05-31 (compiler, dependencies, reference outputs), the data can't tell it apart from the code change. Re-running v2.2.0 on today's CI would settle it. A uniform jump of about two orders of magnitude looks like a numeric precision change in the code.

The **2026-06-14** batch is missing from the export.

Files are in the working directory:
- `analysis.md` – the write-up, with tables and suggested next steps
- `regression_timeline.png` – the plot for the team update: every case per night by worker, with daily failure counts underneath
- `findings.json` – start date 2026-05-31, explained by version, v2.3.0 vs v2.2.0, factor 171.8, both workers, plus stats for all three versions
- `analyze.py` – regenerates the JSON and the plot


## Follow-up

One fix in analysis.md: the line "the before and after distributions don't overlap at all" isn't true as written. The 05-14 v2.2.0 value of 1.38e-7 sits above most of the post-change errors. Please reword it to say that apart from that one outlier there's no overlap. The rest checks out against the numbers.

- `file_edit` G:\Willikers\sandbox\demoforge-csv-analysis-b_41j2mz\working\analysis.md
I fixed it. In the "When it started" section of `analysis.md`, the sentence now reads:

> Apart from the single 05-14 outlier (1.38e-7, covered below), the before and after distributions don't overlap.

The sentence before it says "the worst *normal* v2.2.0 result (8.2e-10)", so it already leaves that outlier out and didn't need changing. I made the same overstatement in my previous summary to you ("don't overlap at all"); the corrected wording applies there too. I didn't change anything else.


## End of conversation

The person had nothing more to ask.


## Done
