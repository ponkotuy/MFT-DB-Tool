import QueryType from "model/QueryType";
import MaxWideFocalLength from "model/query/MaxWideFocalLength";
import MinTelephotoFocalLength from "model/query/MinTelephotoFocalLength";

export interface Lens {
  // レンズID
  id: number
  // レンズメーカー
  maker: string
  // レンズ名
  name: string
  // 品番
  product_number: string
  // 広角端の換算焦点距離[mm]
  wide_focal_length: number
  // 望遠端の換算焦点距離[mm]
  telephoto_focal_length: number
  // 広角端の開放F値
  wide_f_number: number
  // 望遠端の開放F値
  telephoto_f_number: number
  // 広角端の最短撮影距離[mm]
  wide_min_focus_distance: number
  // 望遠端の最短撮影距離[mm]
  telephoto_min_focus_distance: number
  // 最大撮影倍率
  max_photographing_magnification: number
  // フィルター径[mm]
  filter_diameter: number
  // 防塵防滴か？
  is_drip_proof: boolean
  // 手ブレ補正があるか？
  has_image_stabilization: boolean
  // インナーズームか？
  is_inner_zoom: boolean
  // 最大径[mm]
  overall_diameter: number
  // 全長[mm]
  overall_length: number
  // 質量[g]
  weight: number
  // メーカー希望小売価格[円]
  price: number
}

export const QueryTypeList: QueryType[] = [
  new MaxWideFocalLength(),
  new MinTelephotoFocalLength()
];
