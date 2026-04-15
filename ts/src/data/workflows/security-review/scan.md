# Security Review

Scan this codebase for security vulnerabilities. Focus on:

## OWASP Top 10

- **Injection** — SQL injection, command injection, template injection in any language
- **Broken Authentication** — hardcoded credentials, weak token generation, missing auth checks
- **Sensitive Data Exposure** — secrets in source, unencrypted storage, verbose error messages leaking internals
- **XML External Entities (XXE)** — unsafe XML parsing configurations
- **Broken Access Control** — missing authorization checks, IDOR vulnerabilities, privilege escalation paths
- **Security Misconfiguration** — debug modes enabled, default credentials, overly permissive CORS
- **Cross-Site Scripting (XSS)** — unsanitized user input in HTML/template output
- **Insecure Deserialization** — untrusted data passed to deserializers (pickle, yaml.load, JSON.parse with reviver)
- **Using Components with Known Vulnerabilities** — check dependency files for known-vulnerable versions
- **Insufficient Logging & Monitoring** — sensitive operations without audit trails

## Additional checks

- Hardcoded secrets: API keys, passwords, tokens, private keys in source files
- Path traversal: user-controlled input used in file paths without sanitization
- Race conditions: TOCTOU bugs, shared mutable state without synchronization
- Subprocess injection: shell commands built from user input

## Instructions

1. Use Glob to discover all source files
2. Use Grep to search for vulnerability patterns
3. Use Read to examine suspicious files in detail
4. For each confirmed finding:
   - Identify the file and line number
   - Describe the vulnerability and its severity (critical/high/medium/low)
   - Apply a fix using Edit or Write
5. If no findings are discovered, that is a valid outcome — report it

Emit `PRD_EXECUTE_OK` when the scan is complete.
