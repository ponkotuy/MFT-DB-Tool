from decimal import Decimal
from typing import List, MutableMapping, Optional, Dict, Tuple

from pandas import DataFrame
from requests_html import HTMLSession, BaseParser, Element, HTML

from constant import Lens
from service.i_database_service import IDataBaseService
from service.ulitity import regex, load_csv_lens


class DomObject:
    """DOMオブジェクト"""

    def __init__(self, base_parser: BaseParser):
        self.base_parser = base_parser

    def find(self, query: str) -> Optional['DomObject']:
        temp = self.base_parser.find(query, first=True)
        if temp is None:
            return None
        return DomObject(temp)

    def find_all(self, query: str) -> List['DomObject']:
        return [DomObject(x) for x in self.base_parser.find(query)]

    @property
    def text(self) -> str:
        return self.base_parser.text

    @property
    def full_text(self) -> str:
        return self.base_parser.full_text

    # noinspection PyTypeChecker
    @property
    def attrs(self) -> MutableMapping:
        temp: Element = self.base_parser
        return temp.attrs


class ScrapingService:
    """スクレイピング用のラッパークラス"""

    def __init__(self, database: IDataBaseService):
        self.session = HTMLSession()
        self.database = database
        self.database.query('CREATE TABLE IF NOT EXISTS page_cache (url TEXT PRIMARY KEY, text TEXT)')

    def get_page(self, url: str) -> DomObject:
        cache_data = self.database.select('SELECT text from page_cache WHERE url=?', (url,))
        if len(cache_data) == 0:
            temp: HTML = self.session.get(url).html
            print(f'caching... [{url}]')
            self.database.query('INSERT INTO page_cache (url, text) VALUES (?, ?)',
                                (url, temp.raw_html.decode(temp.encoding)))
            return DomObject(temp)
        else:
            return DomObject(HTML(html=cache_data[0]['text']))


def dict_to_lens_for_p(record: Dict[str, str]) -> Lens:
    """辞書型をレンズデータに変換する

    Parameters
    ----------
    record: Dict[str, str]
        辞書型

    Returns
    -------
        レンズデータ
    """

    # 35mm判換算焦点距離
    result1 = regex(record['35mm判換算焦点距離'], r'(\d+)mm～(\d+)mm')
    result2 = regex(record['35mm判換算焦点距離'], r'(\d+)mm')
    if len(result1) > 0:
        wide_focal_length = int(result1[0])
        telephoto_focal_length = int(result1[1])
    else:
        wide_focal_length = int(result2[0])
        telephoto_focal_length = wide_focal_length

    # F値
    result1 = regex(record['レンズ名'], r'F(\d+\.?\d*)-(\d+\.?\d*)')
    result2 = regex(record['レンズ名'], r'F(\d+\.?\d*)')
    if len(result1) > 0:
        wide_f_number = float(result1[0])
        telephoto_f_number = float(result1[1])
    else:
        wide_f_number = float(result2[0])
        telephoto_f_number = wide_f_number

    # 最短撮影距離(m単位のものをmm単位に変換していることに注意)
    result1 = regex(record['最短撮影距離'], r'(\d+\.?\d*)m / (\d+\.?\d*)m')
    result2 = regex(record['最短撮影距離'], r'(\d+\.?\d*)m')
    if len(result1) > 0:
        wide_min_focus_distance = int(Decimal(result1[0]).scaleb(3))
        telephoto_min_focus_distance = int(Decimal(result1[1]).scaleb(3))
    else:
        wide_min_focus_distance = int(Decimal(result2[0]).scaleb(3))
        telephoto_min_focus_distance = wide_min_focus_distance

    # 換算最大撮影倍率
    result = regex(record['最大撮影倍率'], r'：(\d+\.?\d*)')
    max_photographing_magnification = float(result[0])

    # フィルターサイズ
    result = regex(record['フィルターサイズ'], r'φ(\d+)mm')
    if len(result) > 0:
        filter_diameter = int(result[0])
    else:
        filter_diameter = -1

    # 最大径と全長
    result = regex(record['最大径×全長'], r'(\d+\.?\d*)mm[^\d]*(\d+\.?\d*)mm')
    overall_diameter = float(result[0])
    overall_length = float(result[1])

    # 防塵防滴
    is_drip_proof = record['防塵・防滴'].find('○') >= 0 or record['防塵・防滴'].find('〇') >= 0

    # 手ブレ補正
    has_image_stabilization = record['手ブレ補正'].find('O.I.S.') >= 0

    # インナーズーム
    is_inner_zoom = False
    if wide_focal_length == telephoto_focal_length:
        is_inner_zoom = True
    elif record['品番'] in ['H-F007014', 'H-E08018', 'H-PS45175']:
        is_inner_zoom = True

    # 質量
    result = regex(record['質量'], r'([\d,]+)g')
    weight = int(result[0].replace(',', ''))

    # メーカー希望小売価格
    result = regex(record['メーカー希望小売価格'], r'([\d,]+) *円')
    price = int(result[0].replace(',', ''))

    return Lens(
        id=0,
        maker='Panasonic',
        name=record['レンズ名'],
        product_number=record['品番'],
        wide_focal_length=wide_focal_length,
        telephoto_focal_length=telephoto_focal_length,
        wide_f_number=wide_f_number,
        telephoto_f_number=telephoto_f_number,
        wide_min_focus_distance=wide_min_focus_distance,
        telephoto_min_focus_distance=telephoto_min_focus_distance,
        max_photographing_magnification=max_photographing_magnification,
        filter_diameter=filter_diameter,
        is_drip_proof=is_drip_proof,
        has_image_stabilization=has_image_stabilization,
        is_inner_zoom=is_inner_zoom,
        overall_diameter=overall_diameter,
        overall_length=overall_length,
        weight=weight,
        price=price,
        mount='マイクロフォーサーズ',
    )


def get_p_lens_list(scraping: ScrapingService) -> List[Lens]:
    """Panasonic製レンズの情報を取得する

    Parameters
    ----------
    scraping: ScrapingService
        データスクレイピング用クラス

    Returns
    -------
        スクレイピング後のレンズデータ一覧
    """
    # 情報ページを開く
    page = scraping.get_page('https://panasonic.jp/dc/comparison.html')

    # tableタグからデータを収集する
    df = DataFrame()
    for table_element in page.find_all('table'):
        if 'LUMIX G' not in table_element.full_text:
            continue
        df['レンズ名'] = [x.text for x in table_element.find_all('th p')]
        for tr_element in table_element.find_all('tbody > tr'):
            key = tr_element.find('th').text
            value = [x.text for x in tr_element.find_all('td')]
            df[key] = value
        break

    # tableタグの各行を、Lens型のデータに変換する
    return [dict_to_lens_for_p(x) for x in df.to_dict(orient='records')]


def dict_to_lens_for_p_l(record: Dict[str, str]) -> Lens:
    """辞書型をレンズデータに変換する

    Parameters
    ----------
    record: Dict[str, str]
        辞書型

    Returns
    -------
        レンズデータ
    """

    # 焦点距離
    result1 = regex(record['焦点距離'], r'(\d+)-(\d+)mm')
    result2 = regex(record['焦点距離'], r'(\d+)mm')
    if len(result1) > 0:
        wide_focal_length = int(result1[0])
        telephoto_focal_length = int(result1[1])
    else:
        wide_focal_length = int(result2[0])
        telephoto_focal_length = wide_focal_length

    # F値
    result1 = regex(record['レンズ名'], r'F(\d+\.?\d*)-(\d+\.?\d*)')
    result2 = regex(record['レンズ名'], r'F(\d+\.?\d*)')
    if len(result1) > 0:
        wide_f_number = float(result1[0])
        telephoto_f_number = float(result1[1])
    else:
        wide_f_number = float(result2[0])
        telephoto_f_number = wide_f_number

    # 最短撮影距離(m単位のものをmm単位に変換していることに注意)
    result1 = regex(record['撮影距離範囲'], r'(\d+\.?\d*)m-∞.*(\d+\.?\d*)m～∞')
    result2 = regex(record['撮影距離範囲'], r'(\d+\.?\d*)m～∞')
    if len(result1) > 0:
        wide_min_focus_distance = int(Decimal(result1[0]).scaleb(3))
        telephoto_min_focus_distance = int(Decimal(result1[1]).scaleb(3))
    else:
        wide_min_focus_distance = int(Decimal(result2[0]).scaleb(3))
        telephoto_min_focus_distance = wide_min_focus_distance

    # 最大撮影倍率
    result = regex(record['最大撮影倍率'], r'(\d+\.?\d*)倍')
    max_photographing_magnification = float(result[0])

    # フィルターサイズ
    result = regex(record['フィルター径'], r'(\d+)mm')
    if len(result) > 0:
        filter_diameter = int(result[0])
    else:
        filter_diameter = -1

    # 最大径と全長
    result = regex(record['最大径×全長'], r'(\d+\.?\d*)mm[^\d]*(\d+\.?\d*)mm')
    overall_diameter = float(result[0])
    overall_length = float(result[1])

    # 防塵防滴
    is_drip_proof = record['防塵・防滴'].find('○') >= 0 or record['防塵・防滴'].find('〇') >= 0

    # 手ブレ補正
    has_image_stabilization = record['手ブレ補正'].find('I.S.') >= 0

    # インナーズーム
    is_inner_zoom = False
    if wide_focal_length == telephoto_focal_length:
        is_inner_zoom = True
    elif record['品番'] in ['S-E70200', 'S-R70200']:
        is_inner_zoom = True

    # 質量
    result = regex(record['質量'], r'([\d,]+)g')
    weight = int(result[0].replace(',', ''))

    # メーカー希望小売価格
    result = regex(record['メーカー希望小売価格'], r'([\d,]+) *円')
    price = int(result[0].replace(',', ''))

    return Lens(
        id=0,
        maker='Panasonic',
        name=record['レンズ名'],
        product_number=record['品番'],
        wide_focal_length=wide_focal_length,
        telephoto_focal_length=telephoto_focal_length,
        wide_f_number=wide_f_number,
        telephoto_f_number=telephoto_f_number,
        wide_min_focus_distance=wide_min_focus_distance,
        telephoto_min_focus_distance=telephoto_min_focus_distance,
        max_photographing_magnification=max_photographing_magnification,
        filter_diameter=filter_diameter,
        is_drip_proof=is_drip_proof,
        has_image_stabilization=has_image_stabilization,
        is_inner_zoom=is_inner_zoom,
        overall_diameter=overall_diameter,
        overall_length=overall_length,
        weight=weight,
        price=price,
        mount='ライカL',
    )


def get_p_l_lens_list(scraping: ScrapingService) -> List[Lens]:
    """Panasonic製レンズの情報を取得する

    Parameters
    ----------
    scraping: ScrapingService
        データスクレイピング用クラス

    Returns
    -------
        スクレイピング後のレンズデータ一覧
    """
    # 情報ページを開く
    page = scraping.get_page('https://panasonic.jp/dc/comparison.html')

    # tableタグからデータを収集する
    df = DataFrame()
    for table_element in page.find_all('table'):
        if 'LUMIX S' not in table_element.full_text:
            continue
        df['レンズ名'] = [x.text for x in table_element.find_all('th p')]
        for tr_element in table_element.find_all('tbody > tr'):
            key = tr_element.find('th').text
            value = [x.text for x in tr_element.find_all('td')]
            if key == '最大撮影倍率' and len(value) != len(df):
                # 謎の読み取りエラー対策
                fixed_len = min(len(df), len(value))
                df[key] = value[0:fixed_len]
                df['最大径×全長'] = value[fixed_len:]
            else:
                df[key] = value
        break

    # tableタグの各行を、Lens型のデータに変換する
    return [dict_to_lens_for_p_l(x) for x in df.to_dict(orient='records')]


def dict_to_lens_for_o(record: Dict[str, str], record2: Dict[str, str]) -> Lens:
    """辞書型をレンズデータに変換する

    Parameters
    ----------
    record: Dict[str, str]
        辞書型
    record2: Dict[str, str]
        辞書型

    Returns
    -------
        レンズデータ
    """

    # 35mm判換算焦点距離
    result1 = regex(record['焦点距離'], r'換算 *(\d+) *- *(\d+)mm相当')
    result2 = regex(record['焦点距離'], r'換算 *(\d+)mm相当')
    if len(result1) > 0:
        wide_focal_length = int(result1[0])
        telephoto_focal_length = int(result1[1])
    else:
        wide_focal_length = int(result2[0])
        telephoto_focal_length = wide_focal_length

    # F値
    result1 = regex(record['レンズ名'], r'F(\d+\.?\d*)-(\d+\.?\d*)')
    result2 = regex(record['レンズ名'], r'F(\d+\.?\d*)')
    if len(result1) > 0:
        wide_f_number = float(result1[0])
        telephoto_f_number = float(result1[1])
    else:
        wide_f_number = float(result2[0])
        telephoto_f_number = wide_f_number

    # 最短撮影距離(m単位のものをmm単位に変換していることに注意)
    result1 = regex(record['最短撮影距離'], r'(\d+\.\d+) *m.*(\d+\.\d+) *m')
    result2 = regex(record['最短撮影距離'], r'(\d+\.\d+) *m')
    if len(result1) > 0:
        wide_min_focus_distance = int(Decimal(result1[0]).scaleb(3))
        telephoto_min_focus_distance = int(Decimal(result1[1]).scaleb(3))
    else:
        wide_min_focus_distance = int(Decimal(result2[0]).scaleb(3))
        telephoto_min_focus_distance = wide_min_focus_distance

    # 換算最大撮影倍率
    max_photographing_magnification = 0.0
    for key, val in record.items():
        if '最大撮影倍率' not in key:
            continue
        result = regex(val, r'(\d+\.\d+)倍相当')
        for x in result:
            max_photographing_magnification = max(max_photographing_magnification, float(x))
        result = regex(val, r'換算 *(\d+\.\d+)倍')
        for x in result:
            max_photographing_magnification = max(max_photographing_magnification, float(x))

    # フィルターサイズ
    filter_diameter = -1
    for key, val in record.items():
        if 'フィルターサイズ' not in key:
            continue
        result = regex(val, r'(\d+)mm')
        if len(result) > 0:
            filter_diameter = int(result[0])

    # 最大径と全長
    overall_diameter = 0.0
    overall_length = 0.0
    for key, val in record.items():
        if '最大径' not in key:
            continue
        if '全長' not in key and '長さ' not in key:
            continue
        result = regex(val, r'(\d+\.?\d*)')
        if len(result) >= 2:
            overall_diameter = float(result[0])
            overall_length = float(result[1])
            break

    # 防塵防滴
    is_drip_proof = False
    for key, val in record.items():
        if '防滴' in key:
            is_drip_proof = True
            break

    # 手ブレ補正
    has_image_stabilization = 'IS' in record['レンズ名']

    # インナーズーム
    is_inner_zoom = False
    if wide_focal_length == telephoto_focal_length:
        is_inner_zoom = True
    elif record['品番'] in ['7-14_28pro', '40-150_28pro']:
        is_inner_zoom = True

    # 質量
    result = regex(record['質量'], r'([\d,]+)(g|ｇ| g)')
    weight = int(result[0].replace(',', ''))

    # メーカー希望小売価格
    price = int(regex(record2['希望小売価格'], r'([0-9,]+)円')[0].replace(',', ''))

    return Lens(
        id=0,
        maker='OLYMPUS',
        name=record['レンズ名'],
        product_number=record['品番'],
        wide_focal_length=wide_focal_length,
        telephoto_focal_length=telephoto_focal_length,
        wide_f_number=wide_f_number,
        telephoto_f_number=telephoto_f_number,
        wide_min_focus_distance=wide_min_focus_distance,
        telephoto_min_focus_distance=telephoto_min_focus_distance,
        max_photographing_magnification=max_photographing_magnification,
        filter_diameter=filter_diameter,
        is_drip_proof=is_drip_proof,
        has_image_stabilization=has_image_stabilization,
        is_inner_zoom=is_inner_zoom,
        overall_diameter=overall_diameter,
        overall_length=overall_length,
        weight=weight,
        price=price,
        mount='マイクロフォーサーズ',
    )


def get_o_lens_list(scraping: ScrapingService) -> List[Lens]:
    """OLYMPUS製レンズの情報を取得する

    Parameters
    ----------
    scraping: ScrapingService
        データスクレイピング用クラス

    Returns
    -------
        スクレイピング後のレンズデータ一覧
    """

    # レンズのURL一覧を取得する
    page = scraping.get_page('https://www.olympus-imaging.jp/product/dslr/mlens/index.html')
    lens_list: List[Tuple[str, str]] = []
    for a_element in page.find_all('h2.productName > a'):
        lens_name = a_element.text.split('/')[0].replace('\n', '')
        if 'M.ZUIKO' not in lens_name:
            continue
        lens_product_number = a_element.attrs['href'].replace('/product/dslr/mlens/', '').replace('/index.html', '')
        lens_list.append((lens_name, lens_product_number))

    # レンズごとに情報を取得する
    output: List[Lens] = []
    for lens_name, lens_product_number in lens_list:
        # ざっくり情報を取得する
        spec_url = f'https://www.olympus-imaging.jp/product/dslr/mlens/{lens_product_number}/spec.html'
        page = scraping.get_page(spec_url)
        temp_dict: Dict[str, str] = {}
        for th_element, td_element in zip(page.find_all('th'), page.find_all('td')):
            if th_element is None or td_element is None:
                continue
            temp_dict[th_element.text] = td_element.text
        temp_dict['レンズ名'] = lens_name
        temp_dict['品番'] = lens_product_number

        index_url = f'https://www.olympus-imaging.jp/product/dslr/mlens/{lens_product_number}/index.html'
        page = scraping.get_page(index_url)
        temp_dict2: Dict[str, str] = {}
        for th_element, td_element in zip(page.find_all('th'), page.find_all('td')):
            if th_element is None or td_element is None:
                continue
            temp_dict2[th_element.text] = td_element.text

        # 詳細な情報を取得する
        output.append(dict_to_lens_for_o(temp_dict, temp_dict2))
    return output


def dict_to_lens_for_s(record: Dict[str, str]) -> Lens:
    """辞書型をレンズデータに変換する

    Parameters
    ----------
    record: Dict[str, str]
        辞書型

    Returns
    -------
        レンズデータ
    """

    # 35mm判換算焦点距離
    result1 = regex(record['レンズ名'], r'(\d+)mm～(\d+)mm')
    result2 = regex(record['レンズ名'], r'(\d+)mm')
    if len(result1) > 0:
        wide_focal_length = int(result1[0]) * 2
        telephoto_focal_length = int(result1[1]) * 2
    else:
        wide_focal_length = int(result2[0]) * 2
        telephoto_focal_length = wide_focal_length

    # F値
    result1 = regex(record['レンズ名'], r'F(\d+\.?\d*)-(\d+\.?\d*)')
    result2 = regex(record['レンズ名'], r'F(\d+\.?\d*)')
    if len(result1) > 0:
        wide_f_number = float(result1[0])
        telephoto_f_number = float(result1[1])
    else:
        wide_f_number = float(result2[0])
        telephoto_f_number = wide_f_number

    # 最短撮影距離(cm単位のものをmm単位に変換していることに注意)
    result1 = regex(record['最短撮影距離'], r'(\d+\.?\d*)cm / (\d+\.?\d*)cm')
    result2 = regex(record['最短撮影距離'], r'(\d+\.?\d*)cm')
    if len(result1) > 0:
        wide_min_focus_distance = int(Decimal(result1[0]).scaleb(1))
        telephoto_min_focus_distance = int(Decimal(result1[1]).scaleb(1))
    else:
        wide_min_focus_distance = int(Decimal(result2[0]).scaleb(1))
        telephoto_min_focus_distance = wide_min_focus_distance

    # 換算最大撮影倍率
    result = regex(record['最大撮影倍率'], r'(\d+\.?\d*)：(\d+\.?\d*)')
    max_photographing_magnification = round(float(result[0]) * 2 * 100 / float(result[1])) / 100

    # フィルターサイズ
    result = regex(record['フィルターサイズ'], r'φ(\d+)mm')
    if len(result) > 0:
        filter_diameter = int(result[0])
    else:
        filter_diameter = -1

    # 最大径と全長
    result = regex(record['最大径 × 長さ マイクロフォーサーズ'], r'(\d+\.?\d*)mm[^\d]*(\d+\.?\d*)mm')
    overall_diameter = float(result[0])
    overall_length = float(result[1])

    # 防塵防滴
    is_drip_proof = False

    # 手ブレ補正
    has_image_stabilization = 'IS' in record['レンズ名']

    # インナーズーム
    is_inner_zoom = wide_focal_length == telephoto_focal_length

    # 質量
    result = regex(record['質量 マイクロフォーサーズ'], r'([\d,]+)g')
    weight = int(result[0].replace(',', ''))

    # メーカー希望小売価格
    result = regex(record['希望小売価格'], r'([\d,]+) *円')
    price = int(result[0].replace(',', ''))

    return Lens(
        id=0,
        maker='SIGMA',
        name=record['レンズ名'],
        product_number=record['品番'],
        wide_focal_length=wide_focal_length,
        telephoto_focal_length=telephoto_focal_length,
        wide_f_number=wide_f_number,
        telephoto_f_number=telephoto_f_number,
        wide_min_focus_distance=wide_min_focus_distance,
        telephoto_min_focus_distance=telephoto_min_focus_distance,
        max_photographing_magnification=max_photographing_magnification,
        filter_diameter=filter_diameter,
        is_drip_proof=is_drip_proof,
        has_image_stabilization=has_image_stabilization,
        is_inner_zoom=is_inner_zoom,
        overall_diameter=overall_diameter,
        overall_length=overall_length,
        weight=weight,
        price=price,
        mount='マイクロフォーサーズ',
    )


def get_s_lens_list(scraping: ScrapingService) -> List[Lens]:
    """SIGMA製レンズの情報を取得する

    Parameters
    ----------
    scraping: ScrapingService
        データスクレイピング用クラス

    Returns
    -------
        スクレイピング後のレンズデータ一覧
    """

    # レンズのURL一覧を取得する
    page = scraping.get_page('https://www.sigma-global.com/jp/lenses/#/all/micro-four-thirds/')
    lens_list: List[Tuple[str, str]] = []
    for li_element in page.find_all('li.micro-four-thirds'):
        lens_link = 'https://www.sigma-global.com/' + li_element.find('a').attrs['href']
        if 'product' not in lens_link:
            continue
        lens_name = li_element.text.splitlines()[1]
        lens_list.append((lens_name, lens_link))

    # レンズごとに情報を取得する
    output: List[Lens] = []
    for lens_name, lens_link in lens_list:
        # ざっくり情報を取得する
        page = scraping.get_page(lens_link + 'specifications/')
        temp_dict: Dict[str, str] = {}
        th_text = ''
        for tr_element in page.find('table').find_all('tr'):
            th_elements = tr_element.find_all('th')
            if len(th_elements) > 0:
                th_text = th_elements[0].text
            td_elements = tr_element.find_all('td')
            if len(td_elements) == 1:
                temp_dict[th_text] = td_elements[0].text
            elif len(td_elements) == 2:
                temp_dict[th_text + ' ' + td_elements[0].text] = td_elements[1].text
        temp_dict['レンズ名'] = lens_name
        temp_dict['品番'] = lens_link.split('/')[-2]

        # 詳細な情報を取得する
        output.append(dict_to_lens_for_s(temp_dict))
    return output


def dict_to_lens_for_s_l(record: Dict[str, str]) -> Lens:
    """辞書型をレンズデータに変換する

    Parameters
    ----------
    record: Dict[str, str]
        辞書型

    Returns
    -------
        レンズデータ
    """

    # 焦点距離
    result1 = regex(record['レンズ名'], r'(\d+)-(\d+)mm')
    result2 = regex(record['レンズ名'], r'(\d+)mm')
    if len(result1) > 0:
        wide_focal_length = int(result1[0])
        telephoto_focal_length = int(result1[1])
    else:
        wide_focal_length = int(result2[0])
        telephoto_focal_length = wide_focal_length

    # F値
    result1 = regex(record['レンズ名'], r'F(\d+\.?\d*)-(\d+\.?\d*)')
    result2 = regex(record['レンズ名'], r'F(\d+\.?\d*)')
    if len(result1) > 0:
        wide_f_number = float(result1[0])
        telephoto_f_number = float(result1[1])
    else:
        wide_f_number = float(result2[0])
        telephoto_f_number = wide_f_number

    # 最短撮影距離(cm単位のものをmm単位に変換していることに注意)
    result1 = regex(record['最短撮影距離'], r'(\d+\.?\d*).*-.*(\d+\.?\d*).*cm')
    result2 = regex(record['最短撮影距離'], r'(\d+\.?\d*)cm')
    if len(result1) > 0:
        wide_min_focus_distance = int(Decimal(result1[0]).scaleb(1))
        telephoto_min_focus_distance = int(Decimal(result1[1]).scaleb(1))
    else:
        wide_min_focus_distance = int(Decimal(result2[0]).scaleb(1))
        telephoto_min_focus_distance = wide_min_focus_distance

    # 最大撮影倍率
    result1 = regex(record['最大撮影倍率'], r'(\d+\.?\d*)[:：](\d+\.?\d*).*-.*(\d+\.?\d*)[:：](\d+\.?\d*)')
    result2 = regex(record['最大撮影倍率'], r'(\d+\.?\d*)[:：](\d+\.?\d*)')
    if len(result1) > 0:
        temp1 = round(float(result1[0]) * 100 / float(result1[1])) / 100
        temp2 = round(float(result1[2]) * 100 / float(result1[3])) / 100
        max_photographing_magnification = max(temp1, temp2)
    else:
        max_photographing_magnification = round(float(result2[0]) * 100 / float(result2[1])) / 100

    # フィルターサイズ
    if 'フィルターサイズ' in record:
        result = regex(record['フィルターサイズ'], r'φ(\d+)mm')
        if len(result) > 0:
            filter_diameter = int(result[0])
        else:
            filter_diameter = -1
    else:
        filter_diameter = -1

    # 最大径と全長
    result = regex(record['最大径 × 長さ Lマウント'], r'(\d+\.?\d*)mm[^\d]*(\d+\.?\d*)mm')
    overall_diameter = float(result[0])
    overall_length = float(result[1])

    # 防塵防滴
    is_drip_proof = '防塵防滴' in record

    # 手ブレ補正
    has_image_stabilization = 'OS' in record['レンズ名']

    # インナーズーム
    is_inner_zoom = wide_focal_length == telephoto_focal_length

    # 質量
    result = regex(record['質量 Lマウント'], r'([\d,]+)g')
    weight = int(result[0].replace(',', ''))

    # メーカー希望小売価格
    result = regex(record['希望小売価格'], r'([\d,]+) *円')
    price = int(result[0].replace(',', ''))

    return Lens(
        id=0,
        maker='SIGMA',
        name=record['レンズ名'],
        product_number=record['品番'],
        wide_focal_length=wide_focal_length,
        telephoto_focal_length=telephoto_focal_length,
        wide_f_number=wide_f_number,
        telephoto_f_number=telephoto_f_number,
        wide_min_focus_distance=wide_min_focus_distance,
        telephoto_min_focus_distance=telephoto_min_focus_distance,
        max_photographing_magnification=max_photographing_magnification,
        filter_diameter=filter_diameter,
        is_drip_proof=is_drip_proof,
        has_image_stabilization=has_image_stabilization,
        is_inner_zoom=is_inner_zoom,
        overall_diameter=overall_diameter,
        overall_length=overall_length,
        weight=weight,
        price=price,
        mount='ライカL',
    )


def get_s_l_lens_list(scraping: ScrapingService) -> List[Lens]:
    """SIGMA製レンズの情報を取得する

    Parameters
    ----------
    scraping: ScrapingService
        データスクレイピング用クラス

    Returns
    -------
        スクレイピング後のレンズデータ一覧
    """

    # レンズのURL一覧を取得する
    page = scraping.get_page('https://www.sigma-global.com/jp/lenses/#/all/l-mount/')
    lens_list: List[Tuple[str, str]] = []
    for li_element in page.find_all('li.l-mount'):
        lens_link = 'https://www.sigma-global.com/' + li_element.find('a').attrs['href']
        if 'product' not in lens_link:
            continue
        lens_name = li_element.text.splitlines()[1]
        lens_list.append((lens_name, lens_link))

    # レンズごとに情報を取得する
    output: List[Lens] = []
    for lens_name, lens_link in lens_list:
        # ざっくり情報を取得する
        page = scraping.get_page(lens_link + 'specifications/')
        temp_dict: Dict[str, str] = {}
        th_text = ''
        for tr_element in page.find('table').find_all('tr'):
            th_elements = tr_element.find_all('th')
            if len(th_elements) > 0:
                th_text = th_elements[0].text
            td_elements = tr_element.find_all('td')
            if len(td_elements) == 1:
                temp_dict[th_text] = td_elements[0].text
            elif len(td_elements) == 2:
                temp_dict[th_text + ' ' + td_elements[0].text] = td_elements[1].text
        temp_dict['レンズ名'] = lens_name
        temp_dict['品番'] = lens_link.split('/')[-2]

        page = scraping.get_page(lens_link + 'features/')
        if '防塵防滴' in page.full_text:
            temp_dict['防塵防滴'] = '○'

        # 詳細な情報を取得する
        output.append(dict_to_lens_for_s_l(temp_dict))
    return output


def dict_to_lens_for_l_l(record: Dict[str, str]) -> Lens:
    """辞書型をレンズデータに変換する

    Parameters
    ----------
    record: Dict[str, str]
        辞書型

    Returns
    -------
        レンズデータ
    """

    # 品番
    product_number = ''
    if 'Order number' in record:
        product_number = record['Order number'].replace(' ', '')
    if 'Order-number' in record:
        product_number = record['Order-number'].replace(' ', '')

    # 焦点距離
    result1 = regex(record['レンズ名'], r'SL(\d+)–(\d+)')
    result2 = regex(record['レンズ名'], r'SL(\d+)')
    if len(result1) > 0:
        wide_focal_length = int(result1[0])
        telephoto_focal_length = int(result1[1])
    else:
        wide_focal_length = int(result2[0])
        telephoto_focal_length = wide_focal_length

    # F値
    result1 = regex(record['レンズ名'], r'f/(\d+\.?\d*)–(\d+\.?\d*)')
    result2 = regex(record['レンズ名'], r'f/(\d+\.?\d*)')
    if len(result1) > 0:
        wide_f_number = float(result1[0])
        telephoto_f_number = float(result1[1])
    else:
        wide_f_number = float(result2[0])
        telephoto_f_number = wide_f_number

    # 最短撮影距離
    wide_min_focus_distance = 0
    telephoto_min_focus_distance = 0
    temp = record['Working range'].split('\n')
    if len(temp) == 1:
        result1 = regex(temp[0], r'∞ to (\d+\.?\d*) m')
        result2 = regex(temp[0], r'(\d+\.?\d*) m to infinity')
        result3 = regex(temp[0], r'(\d+\.?\d*)mm to infinity')
        if len(result1) > 0:
            wide_min_focus_distance = int(Decimal(result1[0]).scaleb(3))
            telephoto_min_focus_distance = wide_min_focus_distance
        elif len(result2) > 0:
            wide_min_focus_distance = int(Decimal(result2[0]).scaleb(3))
            telephoto_min_focus_distance = wide_min_focus_distance
        elif len(result3) > 0:
            wide_min_focus_distance = int(result3[0])
            telephoto_min_focus_distance = wide_min_focus_distance
    else:
        temp2: Dict[int, int] = {}
        for temp3 in temp:
            result = regex(temp3, r'[Ff]ocal length (\d+) mm: (\d+\.?\d*) m to infinity')
            if len(result) > 0:
                temp2[int(result[0])] = int(Decimal(result[1]).scaleb(3))
        wide_min_focus_distance = temp2[wide_focal_length]
        telephoto_min_focus_distance = temp2[telephoto_focal_length]

    # 最大撮影倍率
    max_photographing_magnification = 0
    temp = record['Largest reproduction ratio'].split('\n')
    if len(temp) == 1:
        result = regex(temp[0], r'(\d+\.?\d*):(\d+\.?\d*)')
        if len(result) > 0:
            max_photographing_magnification = round(float(result[0]) * 100 / float(result[1])) / 100
    else:
        for temp3 in temp:
            result = regex(temp3, r'[Ff]ocal length.*mm: (\d+\.?\d*):(\d+\.?\d*)')
            if len(result) > 0:
                temp3 = round(float(result[0]) * 100 / float(result[1])) / 100
                max_photographing_magnification = max(max_photographing_magnification, temp3)

    # フィルター径
    filter_diameter = int(record['Filter mount'].replace('E', ''))

    # 防塵防滴、手ブレ補正、インナーズーム
    is_drip_proof = False
    has_image_stabilization = 'O.I.S. Performance as per CIPA' in record
    is_inner_zoom = False
    if wide_focal_length == telephoto_focal_length:
        is_inner_zoom = True
    if record['レンズ名'] == 'APO VARIO-ELMARIT-SL90–280 f/2.8–4':
        is_inner_zoom = True

    # 最大径、全長、質量
    overall_diameter = 0
    result = regex(record['Largest diameter'], r'(\d+\.?\d*)[^\d]*mm')
    if len(result) > 0:
        overall_diameter = float(result[0])
    overall_length = 0
    if 'Length to bayonet mount' in record:
        result = regex(record['Length to bayonet mount'], r'(\d+\.?\d*)[^\d]*mm')
        if len(result) > 0:
            overall_length = float(result[0])
    if 'Length to bayonet flange' in record:
        result = regex(record['Length to bayonet flange'], r'(\d+\.?\d*)[^\d]*mm')
        if len(result) > 0:
            overall_length = float(result[0])
    weight = 0
    result = regex(record['Weight'], r'(\d+\.?\d*)[^\d]*g')
    if len(result) > 0:
        weight = float(result[0].replace('.', ''))

    return Lens(
        id=0,
        maker='LEICA',
        name=record['レンズ名'],
        product_number=product_number,
        wide_focal_length=wide_focal_length,
        telephoto_focal_length=telephoto_focal_length,
        wide_f_number=wide_f_number,
        telephoto_f_number=telephoto_f_number,
        wide_min_focus_distance=wide_min_focus_distance,
        telephoto_min_focus_distance=telephoto_min_focus_distance,
        max_photographing_magnification=max_photographing_magnification,
        filter_diameter=filter_diameter,
        is_drip_proof=is_drip_proof,
        has_image_stabilization=has_image_stabilization,
        is_inner_zoom=is_inner_zoom,
        overall_diameter=overall_diameter,
        overall_length=overall_length,
        weight=weight,
        mount='ライカL'
    )


def get_l_l_lens_list(scraping: ScrapingService) -> List[Lens]:
    """ライカ製レンズの情報を取得する

    Parameters
    ----------
    scraping: ScrapingService
        データスクレイピング用クラス

    Returns
    -------
        スクレイピング後のレンズデータ一覧
    """

    # レンズのURL一覧を取得する
    lens_list: List[Tuple[str, str]] = []
    page_list = [
        'https://us.leica-camera.com/Photography/Leica-SL/SL-Lenses/Prime-Lenses',
        'https://us.leica-camera.com/Photography/Leica-SL/SL-Lenses/Vario-Lenses'
    ]
    for page_url in page_list:
        page = scraping.get_page(page_url)
        for div_element in page.find_all('div.h2-text-image-multi-layout.module.no-border'):
            h2_element = div_element.find('h2.headline-40')
            if h2_element is None:
                continue
            span_element = h2_element.find('span')
            if span_element is None:
                continue
            a_element = div_element.find('a.red_cta')
            if a_element is None:
                continue
            lens_name = h2_element.text.replace('\n', '').replace(span_element.text, '')
            lens_url = 'https://us.leica-camera.com' + a_element.attrs['href']
            lens_list.append((lens_name, lens_url))

    # レンズの情報を取得する
    output: List[Lens] = []
    for lens_name, lens_url in lens_list:
        page = scraping.get_page(lens_url)
        temp: Dict[str, str] = {'レンズ名': lens_name}
        section_element = page.find('section.tech-specs')
        if section_element is not None:
            for tr_element in section_element.find_all('tr'):
                td_elements = tr_element.find_all('td')
                if len(td_elements) < 2:
                    continue
                temp[td_elements[0].text] = td_elements[1].text
            output.append(dict_to_lens_for_l_l(temp))
    return output


def get_other_lens_list():
    return load_csv_lens('csv/m4_3.csv', 'マイクロフォーサーズ') + load_csv_lens('csv/l_mount.csv', 'ライカL')
