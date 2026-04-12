# HOPEtensor Production Deploy (Coordinator Stack)

Bu doküman federated Coordinator stack'ini production benzeri şekilde ayağa kaldırmak için hızlı bir runbook sağlar.

## 1) Local production benzeri çalıştırma (Docker Compose)

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

Servisler:
- coordinator: `http://localhost:8000`
- reasoning-a: `http://localhost:8001`
- reasoning-b: `http://localhost:8002`
- verification: `http://localhost:8003`
- ethics: `http://localhost:8004`
- observer: `http://localhost:8005`

## 2) Smoke test

```bash
curl -sS -X POST http://localhost:8000/query \
  -H 'content-type: application/json' \
  -d '{"query":"merhaba hope","client_did":"did:hope:app:demo"}'
```

Beklenen:
- `request_id`, `task_id`, `final_output`, `final_score` alanları,
- `client_did` response içinde geri dönmeli.

## 3) Render deploy

`render.yaml` artık Coordinator + 5 node'u tanımlar.

```bash
render blueprint apply
```

Notlar:
- `hopetensor-coordinator` üzerindeki URL env'leri diğer 5 servisin public URL'lerine işaret etmelidir.
- Üretimde CORS, rate limiting, auth (API key/JWT), central logging ve HTTPS zorunludur.

## 4) Operasyonel checklist

- [ ] `/health` endpoint'leri tüm servislerde 200 döndürüyor.
- [ ] coordinator `/query` için P95 latency takip ediliyor.
- [ ] observer logları merkezi log altyapısına akıyor.
- [ ] timeout değerleri (`HTTP_TIMEOUT_SECONDS`) trafik altında test edildi.
- [ ] rolling deploy / rollback prosedürü doğrulandı.
