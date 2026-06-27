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
grep -R "<REAL_VIN_OR_REG_HERE>" . || true
find . -maxdepth 2 \( -path "./logs" -o -path "./captures" -o -path "./private" \) -print
```

Replace `<REAL_VIN_OR_REG_HERE>` with anything private you want to check. It should print nothing in the public tree.

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

## Tag the known-good build

After the first push:

```bash
git tag v0.3.8
git push origin v0.3.8
```

## Do not commit private captures

Keep private logs/captures outside git, or under ignored folders:

```text
logs/
captures/
private/
```
