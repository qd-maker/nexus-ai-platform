import jwt, time
token = jwt.encode(
    {"sub": "user-123", "exp": int(time.time()) + 3600},
    "HBUY3jnH2REEQxvaYvXT5wIIdBb63DylMPwUXVH4MZh3RLrolXkCfzciVotqW1TsQ6dhJeT15R6a104c1Lvv+g==",
    algorithm="HS256"
)
print(token)