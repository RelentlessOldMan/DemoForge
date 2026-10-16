# Transcript

## Prompt

`kalman_update.m` is the measurement-update routine from our CVT estimator as it
shipped in v2.1.0: a constant-velocity Kalman filter that runs over a stream of
position measurements. Its results are correct, but it's slow, and it dominates the
run time of our validation batches. Production streams are much longer than the
sample here; `test_vectors.csv` is a representative 1500-vector stream and
`model.json` holds the filter model we run it with.

For v2.2.0 I'd like a faster version as `kalman_update_fast.m`, a drop-in
replacement with the same signature, `X = kalman_update_fast(Z, model)`, that works
for whatever model it is given. It must not change the numbers: we need it to agree
with the current routine to within 1e-9 (maximum absolute error).

Please leave a benchmark and equivalence check that compares the two on the sample,
as `benchmark_kalman_update.m`, and a short write-up in `OPTIMIZATION.md` with the
original and optimized runtimes, the speedup, the number of vectors, the maximum
absolute error you measured, and what you changed.


- `$ Get-ChildItem -Force | Format-Table Name,Length; Get-Content kalman_update.m; Get-Content model.json; Get-Content test_vectors.csv -TotalCount 5; (Get-Content test_vectors.csv | Measure-Object -Line).Lines; Get-Command matlab,octave -ErrorAction SilentlyContinue | Select-Object Source`
- `$ cd "G:/Willikers/sandbox/demoforge-matlab-optimization-53q3gq2n/working"; awk -F, 'NR>1{ if(NF!=2 || $1=="" || $2=="" || $1!~/^-?[0-9.]+$/ || $2!~/^-?[0-9.]+$/) print NR": "$0}' test_vectors.csv | head; tail -3 test_vectors.csv; octave --version | head -1`
- `file_write` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\kalman_update_fast.m
- `file_write` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\benchmark_kalman_update.m
- `$ octave --no-gui --quiet --eval "benchmark_kalman_update"`
Benchmark passes: bit-identical on the sample, 56× faster. Quick smoke test of the non-2D measurement branch, then the write-up.

- `$ octave --no-gui --quiet --eval "m.F=eye(3);m.Q=0.01*eye(3);m.R=0.2*eye(3);m.x0=zeros(3,1);m.P0=eye(3);m.H=eye(3);X=kalman_update_fast(randn(50,3),m);disp(size(X));disp(all(isfinite(X(:))));m.H=[1 0 0];m.R=0.2;X=kalman_update_fast(randn(50,1),m);disp(size(X));disp(all(isfinite(X(:))))"`
- `file_write` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\OPTIMIZATION.md
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\OPTIMIZATION.md
I've written `kalman_update_fast.m`, and on the 1500-vector sample its output is bit-identical to the current routine (maximum absolute error 0) and it runs about 56× faster: a median of 5.08 s down to 0.091 s over 5 runs. I measured this in GNU Octave 11.3 because MATLAB isn't installed on this machine. The benchmark script should run unchanged in MATLAB, but I haven't run it there, and MATLAB timings will be different.

**What changed:** the original did every matrix product, sum, transpose and identity with hand-written scalar loops, and nearly all the run time went there. The new version uses MATLAB's built-in matrix operations instead. It also computes `F'`, `H'` and `eye(n)` once rather than on every step, and copies data a row at a time. The maths is the same: the same closed-form 2×2 inverse of S and the same `(I − KH)P` covariance update, which is why the sample results match exactly.

**`benchmark_kalman_update.m`** checks equivalence and fails if the error is over 1e-9. Besides the sample, it compares the two routines on four random models with state sizes 2, 3, 4 and 6 and two measurements each; the largest difference there was 7.6e-13, from the built-in multiply adding things up in a different order. It then times both routines on the sample.

**`OPTIMIZATION.md`** has the runtimes, speedup, number of vectors, measured errors and the list of changes.

On "works for whatever model it is given":
- **Two measurements per step:** any model of this shape is covered and checked against the original.
- **Any other number of measurements:** the current routine fails with an error, so there is nothing to compare against. The fast version handles these by solving against S directly. I only ran it with one and three measurements to confirm it gives finite results, which is not an equivalence check. The write-up says so too.

Run time still grows in proportion to stream length, so production streams will take longer than these sample figures.


## Follow-up

The sample and random-model checks both stop at 1500 and 300 vectors, but production streams are much longer. The tolerance is absolute, so any error grows with position size. Can you add a long-stream check to the benchmark, e.g. 100k+ vectors from the CV model with the real `model.json`, plus a CV model with non-unit dt and non-diagonal R? Then report the max error and the largest |x| it reached.

I'll add a long-stream section to the benchmark. The original routine takes about 3.4 ms per vector, so each 100k-vector reference run needs roughly 6 minutes. With two streams the whole benchmark will take about 12 minutes.

- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\benchmark_kalman_update.m
- `$ octave --no-gui --quiet --eval "benchmark_kalman_update"`
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\OPTIMIZATION.md
I've added the long-stream check to the benchmark. Both 100k-vector streams pass the 1e-9 limit, but the second one passes by only about 3.5×, so longer production streams on models like it could fail.

| Stream (100,000 vectors) | Max abs error | Largest \|x\| | Original | Optimized |
|---|---|---|---|---|
| Real `model.json` (dt = 1) | **0** (bit-identical) | 2.71e6 (position; velocity up to 64) | 400 s | 6.3 s |
| dt = 0.1, R = [0.25 0.10; 0.10 0.16] | **2.81e-10** | 3.50e5 (position; velocity up to 94) | 439 s | 5.9 s |

The sample and random-model checks also still pass.

- **Real model:** it stays bit-identical however long the stream gets. Its F, H, Q, R and P0 contain only 0s, 1s and diagonal terms, so the order the numbers are added in makes no difference.
- **Second model:** here the order does matter. The built-in matrix multiply adds terms in a different order from the original's left-to-right loops, which gives an error of about 5 units in the last place (ulp) at \|x\| = 3.5e5. That error grows in proportion to \|x\|. On similar models, 1e-9 would likely be exceeded somewhere around \|x\| ≈ 1e6. Past \|x\| ≈ 1e7 no implementation that adds in a different order can meet it, because a single ulp is already 1.9e-9 there.

My recommendation is to make the fast version add in exactly the same order as the original. Each matrix product would be built as a running sum over the inner dimension, `C = C + A(:,p)*B(p,:)`, which matches the original's `s = s + A(i,p)*B(p,j)` term by term. The output should then be bit-identical for any model and stream length, so the absolute tolerance no longer depends on \|x\|. It will be somewhat slower than now, though I'd still expect it to be well over 10× faster than the original. Shall I make that change? The alternative is to switch the acceptance criterion to a relative or ulp-based tolerance.

The long section adds about 14 minutes to the benchmark, almost all of it the original routine. You can turn it off with `run_long = false` at the top of the section. I've added these results and the tolerance caveat to `OPTIMIZATION.md`. The sample timings in this run were slower (7.0 s vs 0.11 s, 63×), probably because the machine was busy. I left the earlier figures in the write-up.


## Follow-up

Yes, make the fast version add in exactly the original's order. I'd rather have output that's bit-identical on any model than loosen the tolerance. Then rerun the full benchmark, including both long streams, and update `OPTIMIZATION.md` so every figure comes from that one run. Don't mix in the earlier 56× numbers, and note the machine-load variance if it shows up again.

I'll rewrite the fast version so that every product is accumulated in exactly the original's order, check that it's bit-identical, and then run the full benchmark.

- `file_write` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\kalman_update_fast.m
- `$ octave --no-gui --quiet --eval "Z=dlmread('test_vectors.csv',',',1,0);model=jsondecode(fileread('model.json'));disp(isequal(kalman_update(Z,model),kalman_update_fast(Z,model)));rand('seed',1);randn('seed',1);for n=[2 3 4 6]; A=randn(n);B=randn(2);C=randn(n);m2.F=eye(n)+0.1*randn(n);m2.Q=0.01*(A*A')+1e-3*eye(n);m2.H=randn(2,n);m2.R=0.1*(B*B')+0.05*eye(2);m2.x0=randn(n,1);m2.P0=C*C'+eye(n);Zr=randn(300,2);printf('%d ',isequal(kalman_update(Zr,m2),kalman_update_fast(Zr,m2)));end;disp('');tic;for r=1:5;kalman_update_fast(Z,model);end;disp(toc/5)"`
- `file_write` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\kalman_update_fast.m
I made a mistake in the final covariance product: it reset `P` before reading it and called a helper that doesn't exist. Fixing that now.

- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\kalman_update_fast.m
- `$ octave --no-gui --quiet --eval "Z=dlmread('test_vectors.csv',',',1,0);model=jsondecode(fileread('model.json'));disp(isequal(kalman_update(Z,model),kalman_update_fast(Z,model)));rand('seed',1);randn('seed',1);for n=[2 3 4 6]; A=randn(n);B=randn(2);C=randn(n);m2.F=eye(n)+0.1*randn(n);m2.Q=0.01*(A*A')+1e-3*eye(n);m2.H=randn(2,n);m2.R=0.1*(B*B')+0.05*eye(2);m2.x0=randn(n,1);m2.P0=C*C'+eye(n);Zr=randn(300,2);printf('%d ',isequal(kalman_update(Zr,m2),kalman_update_fast(Zr,m2)));end;disp('');tic;for r=1:5;kalman_update_fast(Z,model);end;disp(toc/5)"`
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-optimization-53q3gq2n/working"; cat > /tmp/fp_probe.m <<'EOF'
  function k = fp_probe(md, N)
    % returns first step k at which posterior P equals previous posterior P bitwise (same arithmetic as original)
    F=md.F;Q=md.Q;H=md.H;R=md.R;P=md.P0;n=size(F,1);
    k = -1;
    for s=1:N
      Pold=P;
      FP=zeros(n);for p=1:n,FP=FP+F(:,p).*P(p,:);end
      P=zeros(n);Ft=F.';for p=1:n,P=P+FP(:,p).*Ft(p,:);end;P=P+Q;
      Ht=H.';PHt=zeros(n,2);for p=1:n,PHt=PHt+P(:,p).*Ht(p,:);end
      S=zeros(2);for p=1:n,S=S+H(:,p).*PHt(p,:);end;S=S+R;
      d=S(1,1)*S(2,2)-S(1,2)*S(2,1);Si=[S(2,2)/d,-S(1,2)/d;-S(2,1)/d,S(1,1)/d];
      K=zeros(n,2);for p=1:2,K=K+PHt(:,p).*Si(p,:);end
      KH=zeros(n);for p=1:2,KH=KH+K(:,p).*H(p,:);end;IKH=eye(n)-KH;
      Pn=zeros(n);for p=1:n,Pn=Pn+IKH(:,p).*P(p,:);end;P=Pn;
      if isequal(typecast(P(:),'uint64'),typecast(Pold(:),'uint64')), k=s; return; end
    end
  end
  EOF
  cp /tmp/fp_probe.m ./fp_probe_tmp.m
  octave --no-gui --quiet --eval "model=jsondecode(fileread('model.json'));disp(fp_probe_tmp(model,5000));dt=0.1;q=0.5;I2=eye(2);cv.F=[I2,dt*I2;zeros(2),I2];cv.Q=q*[dt^3/3*I2,dt^2/2*I2;dt^2/2*I2,dt*I2];cv.H=[I2,zeros(2)];cv.R=[0.25 0.1;0.1 0.16];cv.P0=diag([10 10 100 100]);disp(fp_probe_tmp(cv,5000));rand('seed',1);randn('seed',1);for n=[2 3 4 6]; A=randn(n);B=randn(2);C=randn(n);m2.F=eye(n)+0.1*randn(n);m2.Q=0.01*(A*A')+1e-3*eye(n);m2.H=randn(2,n);m2.R=0.1*(B*B')+0.05*eye(2);m2.P0=C*C'+eye(n);printf('%d ',fp_probe_tmp(m2,5000));end;disp('')"
  rm ./fp_probe_tmp.m
  ```

The production `model.json` reaches an exact fixed point at step 59, but the dt = 0.1 model and three of the random models don't. I'll check whether they settle into a short repeating cycle instead.

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-optimization-53q3gq2n/working"; cat > cyc_probe_tmp.m <<'EOF'
  function [k, L] = cyc_probe_tmp(md, N, Lmax)
    F=md.F;Q=md.Q;H=md.H;R=md.R;P=md.P0;n=size(F,1);
    hist = zeros(n*n, N, 'uint64'); k=-1; L=-1;
    for s=1:N
      FP=zeros(n);for p=1:n,FP=FP+F(:,p).*P(p,:);end
      P=zeros(n);Ft=F.';for p=1:n,P=P+FP(:,p).*Ft(p,:);end;P=P+Q;
      Ht=H.';PHt=zeros(n,2);for p=1:n,PHt=PHt+P(:,p).*Ht(p,:);end
      S=zeros(2);for p=1:n,S=S+H(:,p).*PHt(p,:);end;S=S+R;
      d=S(1,1)*S(2,2)-S(1,2)*S(2,1);Si=[S(2,2)/d,-S(1,2)/d;-S(2,1)/d,S(1,1)/d];
      K=zeros(n,2);for p=1:2,K=K+PHt(:,p).*Si(p,:);end
      KH=zeros(n);for p=1:2,KH=KH+K(:,p).*H(p,:);end;IKH=eye(n)-KH;
      Pn=zeros(n);for p=1:n,Pn=Pn+IKH(:,p).*P(p,:);end;P=Pn;
      hist(:,s)=typecast(P(:),'uint64');
      for l=1:min(Lmax,s-1)
        if isequal(hist(:,s),hist(:,s-l)), k=s; L=l; return; end
      end
    end
    printf('final max|P| %g\n', max(abs(P(:))));
  end
  EOF
  octave --no-gui --quiet --eval "dt=0.1;q=0.5;I2=eye(2);cv.F=[I2,dt*I2;zeros(2),I2];cv.Q=q*[dt^3/3*I2,dt^2/2*I2;dt^2/2*I2,dt*I2];cv.H=[I2,zeros(2)];cv.R=[0.25 0.1;0.1 0.16];cv.P0=diag([10 10 100 100]);[k,L]=cyc_probe_tmp(cv,5000,200);printf('cv: %d %d\n',k,L);rand('seed',1);randn('seed',1);for n=[2 3 4 6]; A=randn(n);B=randn(2);C=randn(n);m2.F=eye(n)+0.1*randn(n);m2.Q=0.01*(A*A')+1e-3*eye(n);m2.H=randn(2,n);m2.R=0.1*(B*B')+0.05*eye(2);m2.P0=C*C'+eye(n);[k,L]=cyc_probe_tmp(m2,3000,200);printf('n=%d: %d %d\n',n,k,L);end"
  rm cyc_probe_tmp.m
  ```

- `file_write` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\kalman_update_fast.m
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-optimization-53q3gq2n/working"; cat > chk_tmp.m <<'EOF'
  function chk_tmp()
    bitsame = @(A,B) isequal(size(A),size(B)) && isequal(typecast(A(:),'uint64'), typecast(B(:),'uint64'));
    Z=dlmread('test_vectors.csv',',',1,0); model=jsondecode(fileread('model.json'));
    printf('sample bit-identical: %d\n', bitsame(kalman_update(Z,model), kalman_update_fast(Z,model)));
    for N=[0 1 2 58 59 60 61]
      printf('N=%d: %d\n', N, bitsame(kalman_update(Z(1:N,:),model), kalman_update_fast(Z(1:N,:),model)));
    end
    dt=0.1;q=0.5;I2=eye(2);cv.F=[I2,dt*I2;zeros(2),I2];cv.Q=q*[dt^3/3*I2,dt^2/2*I2;dt^2/2*I2,dt*I2];
    cv.H=[I2,zeros(2)];cv.R=[0.25 0.1;0.1 0.16];cv.x0=[100;-50;0;0];cv.P0=diag([10 10 100 100]);
    randn('seed',7); Zc = cumsum(randn(3000,2))*3;
    printf('cv 3000: %d\n', bitsame(kalman_update(Zc,cv), kalman_update_fast(Zc,cv)));
    rand('seed',1);randn('seed',1);
    for n=[2 3 4 6]
      A=randn(n);B=randn(2);C=randn(n);m2.F=eye(n)+0.1*randn(n);m2.Q=0.01*(A*A')+1e-3*eye(n);m2.H=randn(2,n);
      m2.R=0.1*(B*B')+0.05*eye(2);m2.x0=randn(n,1);m2.P0=C*C'+eye(n);Zr=randn(1500,2);
      printf('rand n=%d 1500: %d\n', n, bitsame(kalman_update(Zr,m2), kalman_update_fast(Zr,m2)));
    end
    tic; for r=1:5, kalman_update_fast(Z,model); end; printf('sample fast avg %.4f s\n', toc/5);
    tic; kalman_update_fast(Zc,cv); printf('cv 3000 fast %.4f s\n', toc);
  end
  EOF
  octave --no-gui --quiet --eval "chk_tmp"; rm chk_tmp.m
  ```

- `file_read` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\benchmark_kalman_update.m
- `file_write` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\benchmark_kalman_update.m
- `$ octave --no-gui --quiet --eval "benchmark_kalman_update" | Tee-Object -FilePath "$env:TEMP\kalman_bench_run.txt"`
- `file_write` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\OPTIMIZATION.md
- `$ octave --no-gui --quiet --eval "m.F=eye(3);m.Q=0.01*eye(3);m.R=0.2*eye(3);m.x0=zeros(3,1);m.P0=eye(3);m.H=eye(3);X=kalman_update_fast(randn(500,3),m);disp(size(X));disp(all(isfinite(X(:))));m.H=[1 0 0];m.R=0.2;X=kalman_update_fast(randn(500,1),m);disp(size(X));disp(all(isfinite(X(:))))"`
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\OPTIMIZATION.md
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\OPTIMIZATION.md
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\OPTIMIZATION.md
I've rewritten `kalman_update_fast.m` to add in exactly the original's order. The full benchmark now shows its output is bit-identical to the original on every check. That makes it about 31× faster on the sample, down from the earlier version because it no longer uses the built-in matrix multiply. Every figure in `OPTIMIZATION.md` now comes from this one run (Octave 11.3).

| Check | Max abs error | Bit-identical | Largest \|x\| | Original | Optimized |
|---|---|---|---|---|---|
| Sample, 1500 vectors | 0 | yes | 1.50e3 | 4.503 s (median of 5) | 0.147 s → **30.6×** |
| `model.json`, 100k vectors | 0 | yes | 2.71e6 | 307.5 s | 9.14 s (34×) |
| dt = 0.1, non-diagonal R, 100k vectors | 0 | yes | 3.50e5 | 314.0 s | 8.75 s (36×) |
| Random models, n = 2, 3, 4, 6, 1500 vectors each | 0 | yes | — | — | — |

The benchmark now fails unless every check is bit-identical. Since the output matches bit for bit, the 1e-9 limit holds however long the stream is.

**Machine load:** the timings varied by less than 2% across the five runs, so the variance from last time didn't show up. The write-up says so.

**What changed:**
- **Same order of adding:** each matrix product is built with a short loop over the inner dimension, `C = C + A(:,p) .* B(p,:)`. This does the same multiplies and adds in the same order as the original's scalar loops. Moving that loop out of a helper function and into the main loop roughly doubled the speed, because function calls are expensive in Octave.
- **Reusing repeating gains:** P, S and K never depend on the measurements, so the code checks the bits of P after each step against the last 64 steps. Once P repeats exactly, the gains repeat with it, and from then on only the state update is computed. That update uses the same operations in the same order, so the output stays bit-identical.
  - In separate tests outside the benchmark, `model.json` stopped changing at step 59. The dt = 0.1 model fell into a repeating 16-step cycle at step 153.

**Limits:**
- **Models whose P never repeats:** these get no shortcut. The random n = 6 model hadn't repeated after 3000 steps. Such models are still bit-identical, but run much slower than the tables show; I measured about 9× on the sample with that code path alone.
- **MATLAB not tested:** the exact match depends on each multiply and add being rounded separately rather than combined into a single fused operation. That's true in Octave, but I couldn't check it in MATLAB, so run the benchmark there before relying on it.
- **Other measurement sizes:** for anything other than two measurements there is still no original to compare against. I've only confirmed that one and three measurements produce finite results.
- **Run time:** the full benchmark takes about 12 minutes, almost all of it the original routine. `run_long = false` skips the long streams.


## Follow-up

Please add one more case to the benchmark: time the full-computation path on a model whose P never repeats (your n = 6 one, or the sample with the shortcut turned off). Put that speedup in the `OPTIMIZATION.md` results next to the 30.6×, from the same run. Right now the "about 9×" only shows up in chat, and most of the 30× comes from the gain-cycle shortcut, not from the exact-order arithmetic. Anyone reading the write-up should see both numbers before I quote either one.

I'll add an optional third argument that turns off the gain-cycle shortcut. The default behaviour and the two-argument call stay the same. The benchmark can then time the full-computation path on the same sample, so the two numbers are directly comparable.

- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\kalman_update_fast.m
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\kalman_update_fast.m
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\kalman_update_fast.m
Now the benchmark: it checks that the shortcut-off path is bit-identical on the sample, and times all three versions in the same interleaved loop.

- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\benchmark_kalman_update.m
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\benchmark_kalman_update.m
- `$ octave --no-gui --quiet --eval "benchmark_kalman_update" | Tee-Object -FilePath "$env:TEMP\kalman_bench_run2.txt"`
- `file_read` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\OPTIMIZATION.md
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\OPTIMIZATION.md
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\OPTIMIZATION.md
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\OPTIMIZATION.md
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-optimization-53q3gq2n\working\OPTIMIZATION.md
I've added the case: the benchmark now times the sample with the gain-cycle shortcut turned off, and `OPTIMIZATION.md` puts that 9.4× right next to the 30.7×. Every figure in the write-up comes from the same new full run, and every check in it is still bit-identical.

| Sample, 1500 vectors (median of 5, timed in turn) | Runtime | Speedup |
|---|---|---|
| Original | 4.477 s | — |
| Optimized, as shipped | 0.146 s | **30.7×** |
| Optimized, shortcut off | 0.477 s | **9.4×** |

- **How I turned the shortcut off:** `kalman_update_fast(Z, model, false)`. The third argument is optional and defaults to on, so `kalman_update_fast(Z, model)` behaves exactly as before. The benchmark checks that this path is bit-identical on the sample, and it is.
- **Which number to quote:** the write-up says to read the two together. 9.4× is what the exact-order arithmetic gives on its own, and it's the speed you get when a model's covariance never repeats. The rest of the 30.7× comes from the shortcut, because on `model.json` the covariance stops changing at step 59. For a model whose covariance hasn't been checked, the write-up says to quote 9.4×.
- **Machine load showed up this time, on the long streams:**
  - The original took 443.7 s on one long stream and 300.2 s on the other, although it does the same work per step on both. The optimized times barely differed: 8.51 s and 8.55 s.
  - So the 52× on the `model.json` stream is inflated; at the other stream's rate it would be about 35×. The write-up marks this. It also notes that each long-stream timing comes from a single run, and recommends using the sample timings for speedups.
- **Sample timings:** these varied by only about 1%, so load didn't affect them.


## End of conversation

The follow-up limit was reached.


## Done
