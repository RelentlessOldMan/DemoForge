# Transcript

## Prompt

v2.3.0 went out on 30 May, and its release record cites the acceptance campaign
VAL-2026-05: the campaign workbook `validation_results.xlsx` shows ACCEPT. Before the
record is closed, QA wants an independent sign-off review of that workbook against
our validation plan, CVT-VAL-002 Rev A (`validation_plan.md`). Is the ACCEPT right?

Please deliver:

- `validation_results_corrected.xlsx`: the workbook, corrected if anything in it is
  wrong. It's also our template for future campaigns, so keep it formula-driven (no
  pasted values) and don't change the recorded run data.
- `review_note.md`: a short note for the release record with your conclusion and
  what you changed.
- `findings.json`, in this form, with `issues` citing cells of the workbook as you
  received it:

```json
{
  "campaign_verdict": "ACCEPT or REJECT",
  "runs_total": 0,
  "runs_passed": 0,
  "pass_rate": 0.0,
  "failed_runs": ["VR-...."],
  "issues": [{"sheet": "...", "cell": "...", "description": "..."}]
}
```


- `$ ls; Get-Content validation_plan.md; python -c "import openpyxl; print(openpyxl.__version__)"`
- command:

  ```
  python -c "
  import openpyxl
  wb=openpyxl.load_workbook('validation_results.xlsx')
  for ws in wb:
    print('==',ws.title,ws.dimensions, ws.sheet_state)
    for r in ws.iter_rows():
      for c in r:
        if c.value is not None: print(c.coordinate,repr(c.value))
  print(wb.defined_names)
  for ws in wb:
    print(ws.title, ws.conditional_formatting, ws.data_validations.dataValidation, getattr(ws,'tables',{}))
  "
  ```

- command:

  ```
  python -c "
  import openpyxl
  wb=openpyxl.load_workbook('validation_results.xlsx')
  for ws in wb:
    print(ws.title,[ (k,v.hidden) for k,v in ws.row_dimensions.items() if v.hidden],[(k,v.hidden) for k,v in ws.column_dimensions.items() if v.hidden])
    print({c.number_format for r in ws.iter_rows() for c in r})
    print({type(c.value).__name__ for c in ws['F']+ws['G']})
  wb2=openpyxl.load_workbook('validation_results.xlsx',data_only=True)
  print([c.value for c in wb2['Summary']['B']])
  "; Get-Command soffice,libreoffice -ErrorAction SilentlyContinue; Test-Path "C:\Program Files\LibreOffice\program\soffice.exe"
  ```

- command:

  ```
  @'
  import openpyxl
  wb=openpyxl.load_workbook('validation_results.xlsx')
  c,r,s=wb['Criteria'],wb['Runs'],wb['Summary']
  c['B2']=0.5
  for i in range(2,42):
      r[f'H{i}']=f'=IF(AND(F{i}<=Criteria!$B$2,G{i}<=Criteria!$B$4),"PASS","FAIL")'
  N=1000
  s['B5']=f'=COUNTA(Runs!A2:A{N})'
  s['B6']=f'=COUNTIF(Runs!H2:H{N},"PASS")'
  s['B7']=f'=COUNTIF(Runs!H2:H{N},"FAIL")'
  s['B9']=f'=AVERAGE(Runs!F2:F{N})'
  s['B10']=f'=MAX(Runs!F2:F{N})'
  s['B11']=f'=MAX(Runs!G2:G{N})'
  s['B12']='=IF(B8>=Criteria!$B$3,"ACCEPT","REJECT")'
  wb.calculation.fullCalcOnLoad=True
  wb.save('validation_results_corrected.xlsx')
  # independent recompute
  rows=[[x.value for x in row] for row in r.iter_rows(min_row=2,max_row=41)]
  fail=[x[0] for x in rows if not (x[5]<=0.5 and x[6]<=50)]
  n=len(rows);p=n-len(fail)
  print(n,p,p/n,fail, sum(x[5] for x in rows)/n)
  # confirm run data unchanged
  o=openpyxl.load_workbook('validation_results.xlsx')['Runs']; k=openpyxl.load_workbook('validation_results_corrected.xlsx')['Runs']
  print(all(o.cell(i,j).value==k.cell(i,j).value for i in range(1,42) for j in range(1,8)))
  '@ | python -
  ```

- `file_write` G:\Willikers\sandbox\demoforge-excel-investigation-firqar2x\working\findings.json
Writing the review note now; the workbook and findings.json are done.

- `file_write` G:\Willikers\sandbox\demoforge-excel-investigation-firqar2x\working\review_note.md
No, the ACCEPT is wrong. Checked against CVT-VAL-002 Rev A, VAL-2026-05 is a **REJECT**: 34 of 40 runs pass, a pass rate of 0.85 against the 0.95 minimum.

**What went wrong:** on the `Criteria` sheet, cell `B2` sets the position-error limit to **5 m** instead of the plan's **0.5 m**. That let six runs that should have failed count as PASS. All six are `maneuver` runs, with errors from 0.75 to 1.003 m: VR-1901, VR-1903, VR-1904, VR-1917, VR-1929 and VR-1932. In fact every `maneuver` run in the campaign is over the limit. VR-1935 is exactly 0.500 m, so it passes.

Two smaller defects don't change this campaign's result but matter for the template:
- **Runtime check missing:** the PASS/FAIL formula in `Runs!H2:H41` never checks the 50 ms runtime limit, although the plan requires it. Every run here was under the limit anyway (the highest is 43.3 ms).
- **Summary ranges too short:** the formulas in `Summary!B5:B11` only cover rows 2–41. Any run after the 40th in a future campaign would be left out of the totals and the verdict.

Since v2.3.0 shipped on 30 May citing this campaign, QA will need to deal with that before closing the record.

**Changes in the corrected workbook:**
- The limit in `Criteria!B2` is now 0.5.
- The PASS/FAIL formula now checks both error and runtime.
- The summary formulas cover rows 2–1000; blank rows are ignored.
- The summary's verdict formula now references the pass-rate limit with a fixed reference (`Criteria!$B$3`).

Everything is still formula-driven. I checked cell by cell that the recorded run data is identical to the original. I also recalculated the results separately from the run data, and they match: 40 / 34 / 6 / 85.0% / REJECT.

The corrected file was saved without stored results, so it is set to recalculate when opened. In Excel the values appear right away; a viewer that doesn't recalculate will show the summary cells as blank.

Files are in the working folder:
- validation_results_corrected.xlsx
- review_note.md
- findings.json


## Follow-up

I checked findings.json against the plan, and §3/§4 back up the REJECT. Two things are left before I sign:

1. You extended the Summary ranges to row 1000, but the Result formula still only exists in `Runs!H2:H41`. In a 60-run campaign, B5 would count 60 runs while B6/B7 only score the first 40, so the pass rate would be wrong and B6+B7 wouldn't equal B5. Fix this with a formula, not by pasting more rows. Also tell me what you did about blank rows.
2. In the corrected file, what are `Summary!B4` and `B13` now? If B13 still says "D. Volkov, 2026-05-28" next to a REJECT verdict, the workbook claims a sign-off nobody gave. Tell me how you're handling that, and whether B2–B4 are typed-in text or come from the Runs data.

I'll make the Summary compute pass/fail straight from the run data so it doesn't rely on how far column H has been filled, then handle B2–B4 and B13.

- `$ python -c "import formulas" ; if (-not $?) { pip install formulas -q 2>$null | Out-Null; python -c "import formulas; print('ok')" }`
- command:

  ```
  @'
  import openpyxl, copy
  wb=openpyxl.load_workbook('validation_results.xlsx')
  c,r,s=wb['Criteria'],wb['Runs'],wb['Summary']
  c['B2']=0.5
  for i in range(2,42):
      r[f'H{i}']=(f'=IF(A{i}="","",IF(AND(ISNUMBER(F{i}),ISNUMBER(G{i}),'
                  f'F{i}<=Criteria!$B$2,G{i}<=Criteria!$B$4),"PASS","FAIL"))')
  N=1000
  A=f'Runs!$A$2:$A${N}'; B=f'Runs!$B$2:$B${N}'; D=f'Runs!$D$2:$D${N}'
  F=f'Runs!$F$2:$F${N}'; G=f'Runs!$G$2:$G${N}'; H=f'Runs!$H$2:$H${N}'
  s['B3']=f'=IF(COUNTIFS({A},"<>",{D},"<>"&Runs!$D$2)=0,Runs!$D$2,"MIXED BUILDS - check Runs!D")'
  s['B4']=(f'=TEXT(_xlfn.MINIFS({B},{A},"<>"),"yyyy-mm-dd")&" to "&'
           f'TEXT(_xlfn.MAXIFS({B},{A},"<>"),"yyyy-mm-dd")')
  s['B5']=f'=COUNTA({A})'
  s['B6']=f'=COUNTIFS({A},"<>",{F},"<="&Criteria!$B$2,{G},"<="&Criteria!$B$4)'
  s['B7']='=B5-B6'
  s['B8']='=B6/B5'
  s['B9']=f'=AVERAGEIFS({F},{A},"<>")'
  s['B10']=f'=_xlfn.MAXIFS({F},{A},"<>")'
  s['B11']=f'=_xlfn.MAXIFS({G},{A},"<>")'
  s['B12']='=IF(B8>=Criteria!$B$3,"ACCEPT","REJECT")'
  s['B13']=None
  for row,(label,val) in enumerate([
      ('Runs!H completeness check', f'=IF(AND(COUNTIF({H},"PASS")=B6,COUNTIF({H},"FAIL")=B7),"OK","MISMATCH - fill Runs!H formula down to every run")'),
      ('Sign-off', None),
      ('Revision note', 'Re-scored 2026-10-16 against CVT-VAL-002 Rev A. Originally prepared by D. Volkov, 2026-05-28, with verdict ACCEPT, which was based on a wrong limit (5 m) in Criteria!B2. Not signed off.'),
  ],start=14):
      s[f'A{row}']=label; s[f'B{row}']=val
      for col in 'AB':
          s[f'{col}{row}']._style=copy.copy(s[f'{col}13']._style)
  wb.calculation.fullCalcOnLoad=True
  wb.save('validation_results_corrected.xlsx')
  '@ | python -
  ```

Now I'll check the formulas by evaluating them: first the corrected file, then a test copy with 60 runs, a blank row, and the Result column left unfilled past row 41.

- command:

  ```
  @'
  import openpyxl, formulas, datetime, os, shutil
  def evaluate(path):
      xl=formulas.ExcelModel().loads(path).finish()
      sol=xl.calculate()
      out={}
      for k,v in sol.items():
          if "SUMMARY" in k.upper() and "!B" in k.upper():
              out[k.split('!')[-1]]=v.value[0][0] if hasattr(v,'value') else v
      return out
  def show(o):
      for k in sorted(o,key=lambda x:int(x[1:])): print(' ',k,o[k])
  print('corrected file:'); show(evaluate('validation_results_corrected.xlsx'))
  os.makedirs('_t',exist_ok=True)
  wb=openpyxl.load_workbook('validation_results_corrected.xlsx'); r=wb['Runs']
  # rows 42 blank; 43-62 = 20 extra runs, 3 of them failing (one on runtime only, one with missing runtime)
  for k,i in enumerate(range(43,63)):
      err,rt=0.2,40
      if k==0: err=0.9
      if k==1: rt=55
      if k==2: rt=None
      for col,v in zip('ABCDEFG',[f'VR-2{k:03d}',datetime.datetime(2026,5,28),'cruise','v2.3.0-rc1','estimator-01',err,rt]):
          r[f'{col}{i}']=v
  wb.save('_t/test60.xlsx')
  print('60-run test (expect 60 runs, 31+17=48 pass... see below):'); show(evaluate('_t/test60.xlsx'))
  '@ | python - 2>&1 | Select-String -NotMatch "Warning|warn"
  ```

- command:

  ```
  @'
  import openpyxl, formulas
  wb=openpyxl.Workbook(); ws=wb.active; ws.title='S'
  for i,(a,f) in enumerate([('x',1),('y',2),(None,None),('z',3)],start=1):
      ws[f'A{i}']=a; ws[f'B{i}']=f
  ws['D1']='=COUNTIFS(A1:A4,"<>")'      # Excel: 3
  ws['D2']='=COUNTIFS(A1:A4,"?*")'      # Excel: 3
  ws['D3']='=COUNTIFS(B1:B4,"<="&2)'    # Excel: 2
  ws['D4']='=COUNTIFS(A1:A4,"<>",B1:B4,"<=2")'  # Excel: 2
  ws['D5']='=AVERAGEIFS(B1:B4,A1:A4,"<>")'      # Excel: 2
  ws['D6']='=COUNTIFS(A1:A4,"*")'       # Excel: 3
  wb.save('_t/probe.xlsx')
  sol=formulas.ExcelModel().loads('_t/probe.xlsx').finish().calculate()
  for k,v in sorted(sol.items()):
      if '!D' in k: print(k.split('!')[-1], v.value[0][0])
  '@ | python - 2>$null
  ```

- command:

  ```
  @'
  import openpyxl
  wb=openpyxl.load_workbook('validation_results_corrected.xlsx'); s=wb['Summary']
  N=1000
  A=f'Runs!$A$2:$A${N}'; B=f'Runs!$B$2:$B${N}'; D=f'Runs!$D$2:$D${N}'
  F=f'Runs!$F$2:$F${N}'; G=f'Runs!$G$2:$G${N}'; H=f'Runs!$H$2:$H${N}'
  s['B3']=f'=IF(COUNTIF({D},Runs!$D$2)=COUNTA({D}),Runs!$D$2,"MIXED BUILDS - check Runs!D")'
  s['B4']=f'=TEXT(MIN({B}),"yyyy-mm-dd")&" to "&TEXT(MAX({B}),"yyyy-mm-dd")'
  s['B5']=f'=COUNTA({A})'
  s['B6']=(f'=SUMPRODUCT(({A}<>"")*ISNUMBER({F})*ISNUMBER({G})'
           f'*({F}<=Criteria!$B$2)*({G}<=Criteria!$B$4))')
  s['B7']='=B5-B6'
  s['B8']='=B6/B5'
  s['B9']=f'=AVERAGE({F})'
  s['B10']=f'=MAX({F})'
  s['B11']=f'=MAX({G})'
  s['A14']='Data check'
  s['B14']=(f'=IF(AND(COUNT({F})=B5,COUNT({G})=B5,COUNTIF({H},"PASS")=B6,COUNTIF({H},"FAIL")=B7),"OK",'
            f'"CHECK - every run needs a numeric error and runtime, and the Runs!H formula filled down")')
  wb.calculation.fullCalcOnLoad=True
  wb.save('validation_results_corrected.xlsx')
  '@ | python -
  @'
  import openpyxl, formulas, datetime
  def ev(path):
      sol=formulas.ExcelModel().loads(path).finish().calculate()
      o={k.split('!')[-1]:v.value[0][0] for k,v in sol.items() if 'SUMMARY]SUMMARY!B' in k.upper() or "SUMMARY'!B" in k.upper() or k.upper().split('!')[0].endswith('SUMMARY') and '!B' in k.upper()}
      for k in sorted(o,key=lambda x:int(x[1:])):
          if k not in ('B1','B2','B16'): print(' ',k,o[k])
  print('corrected file:'); ev('validation_results_corrected.xlsx')
  wb=openpyxl.load_workbook('validation_results_corrected.xlsx'); r=wb['Runs']
  def add(i,k,err,rt):
      for col,v in zip('ABCDEFG',[f'VR-2{k:03d}',datetime.datetime(2026,5,28),'cruise','v2.3.0-rc1','estimator-01',err,rt]):
          r[f'{col}{i}']=v
  for k,i in enumerate(range(43,63)):           # row 42 left blank
      add(i,k, 0.9 if k==0 else 0.2, 55 if k==1 else 40)
  wb.save('_t/test60.xlsx')
  print('test A: 60 runs, blank row 42, H not filled past 41, extras fail on error x1 and runtime x1  -> expect 60/32/28? no: 34+18=52 pass, 8 fail, 0.8667, CHECK')
  ev('_t/test60.xlsx')
  for i in range(42,63): r[f'H{i}']=r['H41'].value.replace('41',str(i))
  r['G45']=None
  wb.save('_t/test60b.xlsx')
  print('test B: same, H filled down, VR-2002 runtime missing -> expect 60/51/9, CHECK (runtime count)')
  ev('_t/test60b.xlsx')
  '@ | python - 2>$null
  ```

All results match what I expected. Two last checks: a clean 60-run case with column H filled down should show `OK`, and the run data must still be unchanged.

- command:

  ```
  @'
  import openpyxl, formulas
  wb=openpyxl.load_workbook('_t/test60b.xlsx'); wb['Runs']['G45']=40; wb.save('_t/test60c.xlsx')
  sol=formulas.ExcelModel().loads('_t/test60c.xlsx').finish().calculate()
  print({k.split('!')[-1]:v.value[0][0] for k,v in sol.items() if k.upper().endswith(('!B5','!B6','!B7','!B14'))})
  o=openpyxl.load_workbook('validation_results.xlsx')['Runs']; k=openpyxl.load_workbook('validation_results_corrected.xlsx')['Runs']
  print('run data unchanged:', all(o.cell(i,j).value==k.cell(i,j).value for i in range(1,42) for j in range(1,8)), k.max_row)
  s=openpyxl.load_workbook('validation_results_corrected.xlsx')['Summary']
  for i in (2,3,4,13,14,15,16): print(i, s[f'A{i}'].value,'|',s[f'B{i}'].value)
  '@ | python - 2>$null; Remove-Item -Recurse -Force _t -Confirm:$false
  ```

Now updating the review note to match.

- `file_edit` G:\Willikers\sandbox\demoforge-excel-investigation-firqar2x\working\review_note.md
- `file_edit` G:\Willikers\sandbox\demoforge-excel-investigation-firqar2x\working\review_note.md
You were right on both points. I've fixed them and tested the new formulas on the corrected file and on 60-run test copies.

**1. Run counts.** The Summary no longer depends on column H for scoring:
- **Passed (`B6`)** counts rows that have a RunID and are within both the position-error and runtime limits, read directly from the error and runtime columns (rows 2–1000).
- **Failed (`B7`)** is now `Total − Passed`, so the two always add up to `B5`.
- **Column H (`H2:H41`)** still shows PASS/FAIL per row. It now marks a run FAIL if its error or runtime is missing or not a number, and shows blank on rows with no RunID.
- **New "Data check" (`B14`):** shows OK only if every run has a numeric error and runtime and column H agrees with the Summary counts. Otherwise it shows CHECK, so a column H that hasn't been filled down gets flagged.

Test results:

| Case | Total / Passed / Failed | Data check |
|---|---|---|
| Corrected file | 40 / 34 / 6, 0.85, REJECT | OK |
| 60 runs, blank row 42, column H not filled down | 60 / 52 / 8 | CHECK |
| Same, with one runtime missing | 60 / 51 / 9 (missing runtime counted as fail) | CHECK |
| Clean 60 runs, column H filled down | 60 / 52 / 8 | OK |

**Blank rows:** in my first version "blank rows are ignored" was only half true. Completely empty rows were skipped, but nothing caught a run row with missing data. Now empty rows are skipped by every count and statistic, and a run with missing data counts as a fail and trips the Data check.

The Python library I used to check formulas evaluates `"<>"` criteria wrongly even on a 4-row sheet. So I used `SUMPRODUCT`, `COUNT` and `MIN`/`MAX` instead, which I could verify; Excel gives the same results either way.

**2. Summary `B2`–`B4` and `B13`:**
- **`B2` (campaign ID):** still typed in, because the run data doesn't record it.
- **`B3` (build):** now calculated from the Build column; it shows "MIXED BUILDS" if the runs don't all use the same build. It currently reads v2.3.0-rc1.
- **`B4` (period):** now calculated from the earliest and latest run dates; it currently reads 2026-05-20 to 2026-05-27.
- **`B13`:** in my first pass I left it unchanged, so it did show D. Volkov's name next to the REJECT. I've cleared it. A new "Sign-off" row (`B15`) is empty for your signatory. A "Revision note" (`B16`) records that the workbook was prepared by D. Volkov on 2026-05-28, that it originally showed ACCEPT because of the 5 m limit, and that it is not signed off.

I updated `review_note.md` to describe these changes. I left `findings.json` as it was: its issues cite cells in the workbook as received, and `B13` was correct there.


## End of conversation

The person had nothing more to ask.


## Done
