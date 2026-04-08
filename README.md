# SOC Log Clustering

Сервис для кластреизации логов Linux + HDFS TraceBench и автоматическое отнесение новой строки к кластеру при каждом запросе к API. Также возможно добавление сразу всего лог файла построчно с помощью скрипта ingest_file.py Запросы сохраняются в SQL-БД.

## Требования

- Python 3.10+
- Docker
- Каталог `datasets/` с данными LogHub 

## Структура проекта 

- `app/main.py` — маршруты FastAPI
- `app/db/models.py` — схема SQL-таблиц
- `app/core/clustering/pipeline.py` — обучение и предсказание
- `scripts/train_model.py` — офлайн-обучение по `datasets/`
- `scripts/ingest_file.py` — пакетная проверка по файлу
- `artifacts/` — модель и метаданные (в git не хранятся, кроме `.gitkeep`)

## Архитектура

1. **Обучение** -- скрипт `scripts/train_model.py` читает выборку из `datasets/`, строит TF-IDF + MiniBatch K-Means и сохраняет файлы в `artifacts/` (векторизатор, модель, метаданные). Обучение происходит автоматически при старте контейнера. Если в папке `artifacts/` уже присутствует обученная модель, именно она будет использоваться в дальнейшем.

2. **Сервис** — при `POST /api/v1/events` строка нормализуется, векторизуется и автоматически попадает в ближайший кластер. Результат и исходный запрос пишутся в БД

Без папки `artifacts/` с обученной моделью API вернёт `503` на `/api/v1/events`.

### Схема БД

Таблицы описаны в `app/db/models.py`. При старте API вызывается `Base.metadata.create_all()`

Таблицы:

- `user_inference_logs` содержит каждый запрос к `/api/v1/events` (исходная строка, нормализованный текст, `cluster_id`, расстояние)
- `cluster_stats` - сколько раз через API в каждый кластер попали события

## Запуск через Docker Compose
Скопировать каталог проекта

В каталоге проекта должны быть `./datasets` или артефакты внутри `./artifacts`. Если папка будет пустой, то можно оставить ее с `.gitkeep` и модель обучится при первом старте.

```powershell
docker compose up --build
```

API: `http://127.0.0.1:8000`  
PostgreSQL: порт `5432`, пользователь `soc`, пароль `soc`, БД `soc_logs` (при реальном развертываании естественно пароль не стоит хранить так открыто, а лучше задать его через переменные окружения или секреты Docker или Kubernetes).

Строка подключения внутри контейнера `api` уже задана в `docker-compose.yml`.

Я верю, что указала все корректно, поэтому сразу после старта контейнера можно переходить к API запросам. Но ниже указаны доп проверки, что все корректно работает

### 1. Обучение модели

Нужны `datasets/Linux/Linux.log` и хотя бы один `datasets/HDFS_v3_TraceBench/tracebench/*/event.csv`.

```powershell
.\.venv\Scripts\python scripts\train_model.py
```

В `artifacts/` появятся `tfidf_vectorizer.joblib`, `kmeans_model.joblib`, `training_metadata.json`.

### 2. Указать БД и запустить API

Для **PostgreSQL** задайте строку подключения SQLAlchemy, например:

`postgresql+psycopg2://USER:PASS@localhost:5432/soc_logs`

### 3. Проверить, что всё поднялось

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health
```

Ожидается `status: ok`, `model_loaded: true`, `database: ok`, а также блоки **`artifacts`** (наличие файлов векторизатора, модели, `training_metadata.json`) и **`schema_check`** (ожидаемые таблицы и колонки ORM). Если чего-то не хватает, статус будет `degraded`.

Метрики последнего обучения (включая **`cluster_names`** - подписи кластеров):

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/training-metrics
```
### 4. Проверить базу данных SQLite

Запущен контейнер `db` — зайти в `psql` из другого терминала:

```powershell
docker compose exec db psql -U soc -d soc_logs
```
Проверить, создалась ли таблица в `psql`: `\d user_inference_logs`.

Другие примеры:

```sql
\dt
SELECT id, source, cluster_id, cluster_label, distance_to_centroid,
       left(raw_line, 100) AS raw_preview, created_at
FROM user_inference_logs
ORDER BY id DESC
LIMIT 20;

SELECT * FROM cluster_stats ORDER BY api_event_count DESC;
```
## Примеры API-запросов

### Health

**PowerShell**

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health
```

**curl**

```bash
curl -s http://127.0.0.1:8000/health
```

### Метрики обучения

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/training-metrics
```

### Linux

```powershell
$body = @{
  source   = "linux"
  raw_line = "Jun  9 06:06:20 combo kernel: Out of Memory: Killed process 1234 (java)"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/events `
  -Method Post -Body $body -ContentType "application/json"
```

В ответе будут поля **`source`**, **`raw_line`**, **`cluster_name`** (имя кластера, основанное на его содержании, для большей интерпретируемости результата), **`normalized_text`**, **`top_terms`**, метрики и т.д.

**curl**

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/events \
  -H "Content-Type: application/json" \
  -d "{\"source\":\"linux\",\"raw_line\":\"Jun  9 06:06:20 combo kernel: Out of Memory: Killed process 1234 (java)\"}"
```

### HDFS (строка без заголовков)

```powershell
$line = "0795B288B028CAB2,7D3BD4D7234B7C99,getFileInfo,3814841562720638,3814841563756004,10.107.100.57,namenode,Namenode,Success: return(OW[class=class org.apache.hadoop.hdfs.protocol.HdfsFileStatus,value=null])"
$body = @{ source = "hdfs"; raw_line = $line } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/events -Method Post -Body $body -ContentType "application/json"
```

Интерактивная документация OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Отправка файла с логами

Скрипт шлёт каждую строку файла отдельным запросом, кластеризация для каждой строки выполняется на сервере автоматически

**Linux** (первые 100 строк, но можно и не ограничивать):

```powershell
.\.venv\Scripts\python scripts\ingest_file.py --source linux --file datasets/Linux/Linux.log --limit 100 --base-url http://127.0.0.1:8000
```

**HDFS** (`event.csv` чтобы не было проблем с заголовком - `--skip-header`):

```powershell
.\.venv\Scripts\python scripts\ingest_file.py --source hdfs --file "datasets/HDFS_v3_TraceBench/tracebench/NM_DN_w_10DN_30C_1to19B_0to600INT_50RT_10WT/event.csv" --skip-header --limit 200 --base-url http://127.0.0.1:8000
```

## Пояснение к решению

**Python** 
FastAPI отделен от инференса и с базы данных. Так проще писать тесты на нормализаторы и на движок кластеризации без поднятия HTTP и без живой БД, при необходимости изменять код. В качестве альтернативы можно было бы рассмотреть хэндлеры, но такой подход показался мне менее жизнеспособным

**Предобработка текста**
для разных источников заданы отдельные пайплайны (`LinuxLogNormalizer`, `HdfsLogNormalizer`). У них разный синтаксис , следовательно, логично применять разные правила токенизации и маскирования чисел. Так словарь будет более стабильным`TfidfVectorizer` , так как не будет смешения несовместимых шаблонов в одном словарном корпусе

**Векторизация** 
Выполнена  с помощью `sklearn.feature_extraction.text.TfidfVectorizer` с `ngram_range=(1, 2)`, `sublinear_tf=True`, `min_df` / `max_df`. Логарифм по частоте смягчает доминирование повторяющихся токенов. Можно было бы рассмотреть `CountVectorizer`, character n-граммы или нейросетевые эмбеддинги, что, возможно, дало бы даже лучший результат, но я отдала препочтение простому TF-IDF, так как в логах слова часто повторяются и по ним выделить таким методом кластеры достаточно возможно без переусложнения подхода 

**Кластеризация** 
После приведения разреженных векторов к L2-норме евклидово расстояние до центроида близко к метрике, согласованной с косинусной близостью в пространстве признаков. `MiniBatchKMeans` даёт приближение к K-Means с меньшей стоимостью прохода по данным при обучении на десятках тысяч документов. Качество на обучении оценивается суррогатами (silhouette, Davies–Bouldin, inertia на подвыборке) 

**Жизненный цикл модели** 
Обчение происходит только при старте, в файле в `train_model.py`. В рантайме используются исключительно предсказания, без дообучения, и чтение метаданных. Веса сериализуются через `joblib`

**Данные и схема** 
`Base.metadata.create_all()` создаёт таблицы на пустой БД. В ответе API для интерпретации кластера достаточно `cluster_id`, но я также добавила и агрегированное имя из топ-n-грамм центроида и списка `top_terms` из `training_metadata.json`, без хранения по-документного разложения TF-IDF в SQL. 

## Что можно было бы улучшить

Точно можно было бы уделить больше внимания безопасности: аутентификация и авторизация API (ключи, OAuth2/mTLS), TLS, секреты не в репозитории а в хранилищах секретов, установить лимиты запросов и размер тела, настроить пайплайн сбора метрик через Prometheus,  добавить маскирование возможных конфиденциальных данных в логах

**Интеграции** приём событий из очереди (Kafka, например, работали с ней в лабораторных работах), вместо  синхронного HTTP

**Модель и данные** предусмотреть появление новых логов и возможное изменение БД, версионирование артефактов модели и откат, расписание переобучения, контроль дрейфа и качества на отложенной выборке. Влозможно, создать стабильные идентификаторы шаблонов, которые, в отличие от `cluster_id`, не будут меняться при переобучении. Хотя частично `cluster_name` выполняет эту задачу

**Надёжность** несколько реплик API за балансировщиком, резервное копирование БД

## Оценка 
Для оценки качества модели создан эндпоинт `/api/v1/training-metrics`

Получить информацию можно с помощью запроса:
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/training-metrics
```

Полученные мною метрики таковы:
Сводные метрики, которые помогут отслеживать деградацию или стабильность модели в процессе дообучения и эксплуатации:
| Показатель | Значение | Пояснение |
|------------|---------:|---------:|
| Число образцов (`n_samples`) | 24 000 | - |
| Число кластеров (`n_clusters`) | 24 | - |
| Силуэт, подвыборка (`silhouette_sample`) | 0,715 | Чем выше, тем в среднем точки ближе к «своему» кластеру и дальше от соседних, варьируется в промежутке [-1;1] |
| Дэвис–Болдин (`davies_bouldin`) | 1,331 | Чем меньше, тем кластеры обычно компактнее и дальше друг от друга, но абсолютное значение сильно зависит от данных и пространства признаков, поэтому корректнее сравнивать разные итерации обучения модели |
| Инерция K-Means (`inertia`) | 4 696,30 | сумма квадратов расстояний до центроидов в используемом пространстве |

Размерность кластеров:

| Кластер | Событий | Доля, % | Подпись кластера |
|--------:|--------:|--------:|--------:|
| 0 | 838 | 3,49 | num session · for user · session · su |
| 1 | 3 152 | 13,13 | of memory · out of · kernel out · memory killed |
| 2 | 2 227 | 9,28 | num · num num · logname uid · tty nodevssh |
| 3 | 982 | 4,09 | try · try new · new blockreader · op try |
| 4 | 978 | 4,08 | readblock · readblock datanode · datanode · datanode success |
| 5 | 982 | 4,09 | user hadoop · hdfsfile_ blocks · hdfsfile_ · of user |
| 6 | 984 | 4,10 | bestnode · success chosen · chosen · nodes |
| 7 | 212 | 0,88 | num num · num · num pools · pools arcor |
| 8 | 978 | 4,08 | block · success received · receive block · receive |
| 9 | 983 | 4,10 | valid · valid blockreader · newblockreader · return valid |
| 10 | 984 | 4,10 | return op_status_success · op new · op_status_success · new blocksender |
| 11 | 974 | 4,06 | verified · verified by · verifiedbyclient · verifiedbyclient datanode |
| 12 | 984 | 4,10 | choosedatanode dfsclient · choosedatanode · success chosennode · chosennode |
| 13 | 978 | 4,08 | success send · send · send blk_ · sendblock |
| 14 | 978 | 4,08 | checksumok · checksumok dfsclient · dfsclient success · dfsclient |
| 15 | 294 | 1,23 | class · locatedblocks · getblocklocations · protocol locatedblocks |
| 16 | 568 | 2,37 | pass user · pass · num check · check pass |
| 17 | 334 | 1,39 | udev · udev num · node udev · device node |
| 18 | 192 | 0,80 | num num · listening · listening on · named num |
| 19 | 824 | 3,43 | class · protocol hdfsfilestatus · hdfsfilestatus · getfileinfo |
| 20 | 165 | 0,69 | logrotate alert · logrotate · alert · exited abnormally |
| 21 | 2 049 | 8,54 |num · kernel · succeeded · num num |
| 22 | 97 | 0,40 | user task · user user · task · fs copytolocal |
| 23 | 2 263 | 9,43 | num num · num · num connection · connection from |

Также для оценки можно ввести метрику "читабельности" или "понятности": насколько аналитику SOC понятны названия кластеров и насколько они помогают ему в работе?

## Устранение проблем

| Симптом | Что сделать |
|--------|-------------|
| `503` на `/api/v1/events` | Выполнить `python scripts/train_model.py` или проверить, что в `artifacts/` есть `tfidf_vectorizer.joblib` и `kmeans_model.joblib` |
| `404` на `/api/v1/training-metrics` | После обучения должен появиться `artifacts/training_metadata.json` |
| Ошибка подключения к БД | Проверить `DATABASE_URL`, что PostgreSQL запущен или путь к SQLite корректен |
| Пустой или странный ответ для HDFS | Убедиться, что `raw_line` это строка формата `event.csv` и без строки заголовка в теле запроса |


