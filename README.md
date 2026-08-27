El siguiente proyecto representa el trabajo realizado por el EquipoQuetzalito que trata de solucionar la problematica de las microempresas en guatemala y fomentarlas a poder ser empresas formarles, la solucion de este es ofrecerles un sistema relacionado a un CRM que les apoye a realizar calculos de sus ventas y realice predicciones automaticas para poder dar una mejor toma de decisiones al empresario.
La estructura utilizada es la siguiente:
                    EMPRESARIO
                         │
                         ▼
                ┌─────────────────┐
                │   FRONTEND WEB  │
                └────────┬────────┘
                         │
             ┌───────────┴───────────┐
             │                       │
             ▼                       ▼
       DASHBOARD                  CHAT IA
             │                       │
             └───────────┬───────────┘
                         ▼
                    API / BACKEND
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
      BASE DATOS    MOTOR ANALÍTICO   MOTOR ML
          │              │              │
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                 RESULTADOS / MÉTRICAS
                         │
                         ▼
                   RECOMENDACIONES