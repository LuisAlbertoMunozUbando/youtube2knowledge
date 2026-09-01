# Cloudflare edge setup

The API performs long-running media work and must not run inside a Worker. Keep
it on Spark and expose it through a Cloudflare Tunnel.

1. Create a tunnel in Cloudflare Zero Trust.
2. Route a hostname such as `youtube2knowledge-api.example.com` to
   `http://localhost:8020` on Spark.
3. Set API `CORS_ORIGINS` to the exact Vercel production URL and custom web
   domain. Do not use `*`.
4. Set Vercel `NEXT_PUBLIC_API_BASE_URL` to the tunnel hostname.
5. Configure a WAF rate-limit rule for `POST /api/v1/jobs`.

Suggested tunnel ingress:

```yaml
ingress:
  - hostname: youtube2knowledge-api.example.com
    service: http://localhost:8020
  - service: http_status:404
```

Do not place OpenAI, NVIDIA, or transcription API keys in Vercel. They belong
only in the API environment on Spark.
