# Gateway rejections

1. Tách 401, 403, 413, 429 và upstream timeout theo metric.
2. Kiểm tra Keycloak/JWKS, role và quota; không ghi token vào log.
3. Chỉ thay policy sau khi có request ID và actor audit tương ứng.
