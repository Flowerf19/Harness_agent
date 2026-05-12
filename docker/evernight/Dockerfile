FROM base

COPY --chown=march7_user:march7_group twin/ /app/twin/
COPY --chown=march7_user:march7_group gateway/ /app/gateway/

CMD ["python", "-m", "twin.evernight"]
