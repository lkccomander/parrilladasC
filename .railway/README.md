# Railway infrastructure

This directory manages the existing `parrilladasC` production project. Runtime code deploys from GitHub `main`; infrastructure changes require a separate plan and apply.

From the repository root:

```sh
npm ci --prefix .railway
npm run --prefix .railway plan
npm run --prefix .railway apply
```

Review every plan. Keep all existing services and the PostgreSQL volume in `railway.ts`; omitting resources can delete them. Variables are unmanaged and remain on Railway. Do not import secret values into source.

The local CLI wrapper resolves the pinned CLI and Node executables consistently on Windows and Linux. The lock file pins both the CLI and SDK.

See [deployment instructions](../docs/railway.md) for service configuration, verification and operational limits.
