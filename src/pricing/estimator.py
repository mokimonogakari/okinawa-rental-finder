"""賃料推定モデル - Ridge回帰 + Random Forest"""

import json
import logging
import pickle
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler

from src.pricing.features import build_features, get_target

logger = logging.getLogger(__name__)


class RentEstimator:
    """賃料推定モデル"""

    def __init__(self, model_dir: str | Path = "./data/models"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.ridge_model = None
        self.rf_model = None
        self.scaler = StandardScaler()
        self.feature_columns: list[str] = []
        self.is_fitted = False

    def train(
        self,
        property_df: pd.DataFrame,
        land_price_df: pd.DataFrame | None = None,
        test_size: float = 0.2,
    ) -> dict:
        """モデルを学習"""
        logger.info(f"学習データ: {len(property_df)}件")

        # 特徴量構築
        X = build_features(property_df, land_price_df)
        y = get_target(property_df)

        # 有効なデータのみ使用
        valid_mask = y.notna() & (y > 0) & X.notna().all(axis=1)
        X = X[valid_mask].reset_index(drop=True)
        y = y[valid_mask].reset_index(drop=True)

        if len(X) < 50:
            logger.warning(f"学習データが不足しています ({len(X)}件)。最低50件必要です。")
            return {"error": "insufficient_data", "count": len(X)}

        self.feature_columns = list(X.columns)

        # データ分割
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )

        # スケーリング
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # --- Ridge回帰 ---
        self.ridge_model = Ridge(alpha=1.0)
        self.ridge_model.fit(X_train_scaled, y_train)
        ridge_pred = self.ridge_model.predict(X_test_scaled)

        ridge_metrics = {
            "r2": r2_score(y_test, ridge_pred),
            "mae": mean_absolute_error(y_test, ridge_pred),
            "rmse": np.sqrt(mean_squared_error(y_test, ridge_pred)),
        }
        logger.info(f"Ridge回帰 - R²: {ridge_metrics['r2']:.3f}, MAE: {ridge_metrics['mae']:.0f}円")

        # --- Random Forest ---
        self.rf_model = RandomForestRegressor(
            n_estimators=100,
            max_depth=15,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
        )
        self.rf_model.fit(X_train, y_train)
        rf_pred = self.rf_model.predict(X_test)

        rf_metrics = {
            "r2": r2_score(y_test, rf_pred),
            "mae": mean_absolute_error(y_test, rf_pred),
            "rmse": np.sqrt(mean_squared_error(y_test, rf_pred)),
        }
        logger.info(f"RandomForest - R²: {rf_metrics['r2']:.3f}, MAE: {rf_metrics['mae']:.0f}円")

        # 特徴量重要度 (Random Forest)
        importances = dict(zip(
            self.feature_columns,
            self.rf_model.feature_importances_.tolist(),
        ))
        top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:10]

        self.is_fitted = True

        # モデル保存
        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._save_model(version)

        return {
            "ridge": ridge_metrics,
            "random_forest": rf_metrics,
            "training_samples": len(X_train),
            "test_samples": len(X_test),
            "total_features": len(self.feature_columns),
            "top_features": top_features,
            "version": version,
        }

    def predict(
        self,
        property_df: pd.DataFrame,
        land_price_df: pd.DataFrame | None = None,
        model_type: str = "random_forest",
    ) -> pd.DataFrame:
        """賃料を推定"""
        if not self.is_fitted:
            raise RuntimeError("モデルが学習されていません。先にtrain()を実行してください。")

        X = build_features(property_df, land_price_df)

        # 学習時のカラムに合わせる
        for col in self.feature_columns:
            if col not in X.columns:
                X[col] = 0
        X = X[self.feature_columns]

        if model_type == "ridge":
            X_scaled = self.scaler.transform(X)
            predictions = self.ridge_model.predict(X_scaled)
        else:
            predictions = self.rf_model.predict(X)

        result = property_df[["rent"]].copy() if "rent" in property_df.columns else pd.DataFrame()
        result["estimated_rent"] = np.round(predictions).astype(int)

        # 割安度スコア (実際賃料 / 推定賃料)
        if "rent" in property_df.columns:
            actual = pd.to_numeric(property_df["rent"], errors="coerce")
            result["affordability_score"] = np.round(
                actual / result["estimated_rent"].clip(lower=1), 3
            )
            result["price_diff"] = actual - result["estimated_rent"]
            result["price_diff_pct"] = np.round(
                (result["price_diff"] / result["estimated_rent"].clip(lower=1)) * 100, 1
            )

        # 信頼区間 (Random Forestの各木の予測を使用)
        if model_type == "random_forest" and self.rf_model is not None:
            tree_predictions = np.array([
                tree.predict(X) for tree in self.rf_model.estimators_
            ])
            result["ci_lower"] = np.round(np.percentile(tree_predictions, 5, axis=0)).astype(int)
            result["ci_upper"] = np.round(np.percentile(tree_predictions, 95, axis=0)).astype(int)

        return result

    def predict_single(
        self, property_data: dict, land_price_df: pd.DataFrame | None = None,
    ) -> dict:
        """単一物件の賃料を推定"""
        df = pd.DataFrame([property_data])
        result = self.predict(df, land_price_df)
        return result.iloc[0].to_dict()

    def get_feature_importances(self) -> list[tuple[str, float]]:
        """特徴量重要度を取得"""
        if self.rf_model is None:
            return []
        importances = dict(zip(self.feature_columns, self.rf_model.feature_importances_))
        return sorted(importances.items(), key=lambda x: x[1], reverse=True)

    def get_price_factors(self, property_data: dict) -> dict:
        """物件の価格影響因子を分析"""
        if self.ridge_model is None:
            return {}

        df = pd.DataFrame([property_data])
        X = build_features(df)
        for col in self.feature_columns:
            if col not in X.columns:
                X[col] = 0
        X = X[self.feature_columns]

        X_scaled = self.scaler.transform(X)
        contributions = X_scaled[0] * self.ridge_model.coef_

        factors = {}
        for col, contrib in zip(self.feature_columns, contributions):
            if abs(contrib) > 100:  # 100円以上の影響がある特徴量のみ
                factors[col] = round(float(contrib))

        return dict(sorted(factors.items(), key=lambda x: abs(x[1]), reverse=True)[:10])

    def _save_model(self, version: str):
        """モデルをファイルに保存"""
        model_data = {
            "ridge_model": self.ridge_model,
            "rf_model": self.rf_model,
            "scaler": self.scaler,
            "feature_columns": self.feature_columns,
            "version": version,
        }
        filepath = self.model_dir / f"rent_model_{version}.pkl"
        with open(filepath, "wb") as f:
            pickle.dump(model_data, f)
        logger.info(f"モデル保存: {filepath}")

    def load_model(self, version: str | None = None):
        """モデルをファイルから読み込み"""
        if version:
            filepath = self.model_dir / f"rent_model_{version}.pkl"
        else:
            # 最新モデルを自動選択
            model_files = sorted(self.model_dir.glob("rent_model_*.pkl"))
            if not model_files:
                raise FileNotFoundError("学習済みモデルが見つかりません")
            filepath = model_files[-1]

        with open(filepath, "rb") as f:
            data = pickle.load(f)

        self.ridge_model = data["ridge_model"]
        self.rf_model = data["rf_model"]
        self.scaler = data["scaler"]
        self.feature_columns = data["feature_columns"]
        self.is_fitted = True
        logger.info(f"モデル読み込み: {filepath}")
