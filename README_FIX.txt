ETF page not updating — confirmed repair

GitHub already has etf_consolidation.py. Its workflow is still the OLD version.
You need to edit one existing file in GitHub.

1. Open https://github.com/rs88pvyhzz-code/market-terminal/blob/main/.github/workflows/publish.yml
2. Click pencil (Edit). Delete all text and paste the contents of the enclosed .github/workflows/publish.yml.
3. Click Commit changes (directly to main).
4. Go to Actions > Refresh and publish Market Terminal > Run workflow.
5. Wait for a green check, then refresh the published site.

Verify the edited GitHub workflow includes:
python install_etf_trackers.py --repo . && python etf_consolidation.py --repo . && python build_terminal.py --years 20

The prior workflow ran install_etf_trackers.py straight into build_terminal.py.
That skipped the consolidated dataset and compact layout completely.

No changes to main source files needed, etf_consolidation.py already exists.
