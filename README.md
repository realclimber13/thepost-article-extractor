# The Post article extractor

Runs at :01 and :31 UTC (after The Post's existing half-hour NewsAPI refresh), on manual dispatch, and when extractor files change on main. GitHub may delay scheduled runners.

Uses free Trafilatura on a public GitHub Actions runner. Attempts up to 40 saved article URLs concurrently, with one request at a time per original publisher. Respects robots.txt, public HTTP destinations, response-size limits and access failures. It does not bypass paywalls, security challenges or rate limits. No guarantee that every publisher supplies its complete article.

GitHub OIDC authenticates only this repository's main-branch workflow to The Post. No repository secrets or NewsAPI/NVIDIA keys are required. Article text is sent directly to the Site, never committed or uploaded as an artifact. Failed extraction keeps the previous text. The Site queues NVIDIA reports using its existing credentials and rewrite scheduler.

The workflow never calls NewsAPI or sends newsletters. Duplicate batch claims are skipped. Check the Actions run summary for imported and skipped counts. Public repository Actions schedules may be disabled by GitHub after prolonged repository inactivity; re-enable in Actions if needed.
