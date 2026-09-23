SIGL Letter Desk Microsoft Teams app package

This package contains:
- manifest.json
- color.png
- outline.png

Before production use:
1. Host the Letter Desk at a reachable HTTPS URL.
2. Replace YOUR-HTTPS-HOSTNAME.example.com in manifest.json:
   - staticTabs[0].contentUrl
   - staticTabs[0].websiteUrl
   - validDomains[0]
3. Recreate the ZIP with all three files at its root.
4. Upload the ZIP in Teams:
   Apps -> Manage your apps -> Upload an app.

The current placeholder URL will not work until replaced.
The local address http://127.0.0.1:5000 cannot be used by Teams.
