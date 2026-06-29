# Move to ~/github and push

Project name used for GitHub:

```text
bkd-tp20-diag
```

## Move/copy into ~/github

From the directory containing `bkd_tp20_project`:

```bash
mkdir -p ~/github
rm -rf ~/github/bkd-tp20-diag
cp -a bkd_tp20_project ~/github/bkd-tp20-diag
cd ~/github/bkd-tp20-diag
```

## Check private files are not present

```bash
git grep -nE 'YOUR_REAL_VIN|YOUR_REG|your-name|your-email|your-handle' || echo "No tracked personal strings found"
git ls-files | grep -E 'logs|captures|private|\.venv|egg-info|__pycache__' || echo "No private/generated paths tracked"
```

Adjust the private-string list for your own VINs, registrations, names, handles, and
workshop/customer details.

## Initialise git

```bash
git init
git branch -M main
git status
git add .
git commit -m "Initial public BKD TP2.0 diagnostic tool"
```

## Create GitHub repo with GitHub CLI

If `gh` is installed and authenticated:

```bash
gh repo create bkd-tp20-diag --public --source=. --remote=origin --push
```

For a private repo instead:

```bash
gh repo create bkd-tp20-diag --private --source=. --remote=origin --push
```

## Or push to an already-created GitHub repo

Replace `YOUR_GITHUB_USERNAME`:

```bash
git remote add origin git@github.com:YOUR_GITHUB_USERNAME/bkd-tp20-diag.git
git push -u origin main
```

HTTPS alternative:

```bash
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/bkd-tp20-diag.git
git push -u origin main
```

If the remote already has an older public checkpoint, fetch and merge it rather than
blindly overwriting it:

```bash
git fetch origin
git log --oneline --decorate --graph --all --max-count=20
git merge --allow-unrelated-histories origin/main -m "Merge existing GitHub main"
```

For add/add conflicts where the local tested tree should win:

```bash
git checkout --ours .
git add .
git commit
```

Then push:

```bash
git push -u origin main
```

## Tag known-good builds

Known useful checkpoints:

```text
v0.3.8   old public/docs checkpoint
v0.3.16  multi-module read-only diagnostics and ABS clean-exit checkpoint
v0.3.17  observed DTC lookup entries
v0.4.0   interactive start menu checkpoint
```

Push tags:

```bash
git push origin v0.3.16 v0.3.17 v0.4.0
```

If a tag was corrected locally before publishing:

```bash
git push -f origin v0.3.16 v0.3.17 v0.4.0
```

## Do not commit private captures

Keep private logs/captures outside git, or under ignored folders:

```text
logs/
captures/
private/
```
