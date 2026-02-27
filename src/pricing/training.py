"""モデル学習パイプライン"""

import json
import logging
from pathlib import Path

import pandas as pd
import yaml

from src.database.models import get_connection
from src.database.repository import LandPriceRepository, PropertyRepository
from src.pricing.estimator import RentEstimator
from src.pricing.land_price import fetch_and_store_land_prices

logger = logging.getLogger(__name__)


def run_training_pipeline(config_path: str = "./config/settings.yaml"):
    """モデル学習パイプライン全体を実行"""
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    db_path = config["database"]["path"]
    conn = get_connection(db_path)

    # 1. 物件データ取得
    prop_repo = PropertyRepository(conn)
    training_data = prop_repo.get_training_data()
    logger.info(f"学習用物件データ: {len(training_data)}件")

    if len(training_data) < 50:
        logger.warning("学習データ不足 (最低50件)。スクレイピングを先に実行してください。")
        conn.close()
        return None

    property_df = pd.DataFrame(training_data)

    # 2. 地価データ取得
    land_repo = LandPriceRepository(conn)
    land_rows = conn.execute("SELECT * FROM land_prices").fetchall()
    land_price_df = pd.DataFrame([dict(r) for r in land_rows]) if land_rows else None

    # 3. モデル学習
    estimator = RentEstimator(model_dir=config.get("pricing", {}).get("model_dir", "./data/models"))
    results = estimator.train(property_df, land_price_df)

    if "error" in results:
        logger.error(f"学習失敗: {results}")
        conn.close()
        return results

    # 4. モデルメタデータ保存
    conn.execute(
        "UPDATE model_metadata SET is_active = 0 WHERE is_active = 1"
    )
    conn.execute(
        """INSERT INTO model_metadata
           (model_type, version, training_samples, r2_score, mae, rmse,
            feature_importances_json, model_path, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (
            "random_forest",
            results["version"],
            results["training_samples"],
            results["random_forest"]["r2"],
            results["random_forest"]["mae"],
            results["random_forest"]["rmse"],
            json.dumps(results["top_features"], ensure_ascii=False),
            f"./data/models/rent_model_{results['version']}.pkl",
        ),
    )
    conn.commit()

    # 5. 全物件の推定賃料を更新
    logger.info("全物件の推定賃料を更新中...")
    all_properties = prop_repo.search(limit=10000)
    if all_properties:
        all_df = pd.DataFrame(all_properties)
        predictions = estimator.predict(all_df, land_price_df)

        for idx, row in predictions.iterrows():
            prop_id = all_properties[idx]["id"]
            est_rent = int(row.get("estimated_rent", 0))
            score = float(row.get("affordability_score", 1.0))
            if est_rent > 0:
                prop_repo.update_estimation(prop_id, est_rent, score)

    conn.close()
    logger.info(f"学習完了 - R²: {results['random_forest']['r2']:.3f}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_training_pipeline()
