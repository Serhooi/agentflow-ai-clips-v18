# План миграции на Render.com для 100+ пользователей

## Текущее состояние
- ✅ Продукт работает на Render.com
- ✅ 512MB RAM оптимизация
- ✅ Гибридная очередь (память/Redis)
- ✅ Лимит: 2 одновременные задачи

## Этап 1: Добавление Redis (без простоя)

### 1.1 Добавить Redis сервис в Render.com

В Render Dashboard:
1. **New** → **Redis**
2. **Name:** `agentflow-redis`
3. **Plan:** `Starter` ($7/месяц, 25MB)
4. **Region:** тот же что и основной сервис

### 1.2 Добавить переменную окружения

В настройках Web Service:
```
REDIS_URL=redis://red-xxxxx:6379
```
(URL скопировать из Redis сервиса)

### 1.3 Результат
- Система автоматически переключится на Redis
- Очередь станет персистентной
- Никакого простоя!

## Этап 2: Добавление воркеров (масштабирование)

### 2.1 Создать Background Worker сервис

В Render Dashboard:
1. **New** → **Background Worker**
2. **Name:** `agentflow-worker-1`
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `python worker.py`
5. **Instance Type:** `Starter` (512MB, $7/месяц)

### 2.2 Создать worker.py

```python
# worker.py - Воркер для обработки задач
import asyncio
import logging
from app import hybrid_queue, analyze_video_internal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

async def worker_main():
    """Основной цикл воркера"""
    logger.info("🔄 Воркер запущен")
    
    while True:
        try:
            # Получаем задачу из очереди
            task = hybrid_queue.get_task()
            
            if task:
                task_id = task["task_id"]
                video_id = task["video_id"]
                
                logger.info(f"🎬 Обрабатываем задачу: {task_id}")
                
                try:
                    # Обрабатываем видео
                    result = await analyze_video_internal(video_id)
                    
                    # Сохраняем результат
                    hybrid_queue.complete_task(task_id, {
                        "status": "completed",
                        "result": result,
                        "completed_at": datetime.now().isoformat()
                    })
                    
                    logger.info(f"✅ Задача завершена: {task_id}")
                    
                except Exception as e:
                    # Сохраняем ошибку
                    hybrid_queue.complete_task(task_id, {
                        "status": "failed",
                        "error": str(e),
                        "failed_at": datetime.now().isoformat()
                    })
                    logger.error(f"❌ Ошибка задачи {task_id}: {e}")
            else:
                # Если задач нет, ждем
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"❌ Ошибка воркера: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(worker_main())
```

### 2.3 Масштабирование воркеров

Создать несколько воркеров:
- `agentflow-worker-1` 
- `agentflow-worker-2`
- `agentflow-worker-3`

**Итого:** 3 воркера × 2 задачи = 6 одновременных задач

## Этап 3: Модификация API (переключение на очередь)

### 3.1 Изменить эндпоинт анализа

Вместо прямой обработки → добавление в очередь:

```python
@app.post("/api/videos/analyze")
async def analyze_video_queue(request: AnalyzeRequest):
    """Анализ через очередь"""
    try:
        # Добавляем в очередь вместо прямой обработки
        task_id = hybrid_queue.add_task({
            "video_id": request.video_id,
            "type": "analyze"
        })
        
        return {
            "task_id": task_id,
            "status": "queued",
            "message": "Задача добавлена в очередь"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos/task/{task_id}/status")
async def get_task_status_queue(task_id: str):
    """Статус задачи из очереди"""
    result = hybrid_queue.get_task_result(task_id)
    
    if not result:
        return {"status": "processing", "progress": 0}
    
    return result
```

## Результат миграции

### До миграции:
- **Пропускная способность:** 2 задачи одновременно
- **Пользователи:** ~5-10 комфортно
- **Стоимость:** $7/месяц

### После миграции:
- **Пропускная способность:** 6-10 задач одновременно  
- **Пользователи:** 50-80 комфортно
- **Стоимость:** $35/месяц ($7 API + $7 Redis + $21 воркеры)

### При необходимости дальнейшего масштабирования:
- Добавить еще воркеров (по $7 каждый)
- Увеличить Redis план
- **100+ пользователей:** ~$50-70/месяц

## Мониторинг

### Новые эндпоинты:
- `GET /api/system/queue-stats` - статистика очереди
- `GET /health` - состояние системы
- `GET /api/system/stats` - детальная статистика

### Алерты:
- Длина очереди > 10 задач
- Память > 80%
- Воркеры не отвечают

## Rollback план

Если что-то пойдет не так:
1. Убрать переменную `REDIS_URL`
2. Система автоматически вернется к памяти
3. Остановить воркеры
4. Все работает как раньше!

## Временная шкала

- **День 1:** Добавить Redis (5 минут)
- **День 2:** Создать первого воркера
- **День 3:** Протестировать нагрузку
- **День 4:** Добавить остальных воркеров
- **День 5:** Переключить API на очередь

**Итого:** 1 неделя без простоя сервиса!