import React, { useState, useEffect } from 'react';
import { Container, Row, Col, Table, Form, Button } from 'react-bootstrap';
import { Decimal } from 'decimal.js';
import 'App.css';
import { Lens, QueryTypeList, MilliMeterToMeterQueryTypeList, BooleanQueryTypeList, Query } from 'constant';
import { createQuery, calcFilteredLensList, parseFloat2 } from 'utility';
import QueryButton from 'component/QueryButton';

/** メインとなるComponent */
const App: React.FC = () => {
  // フィルタ前のレンズ一覧
  const [lensList, setLensList] = useState<Lens[]>([]);
  // フィルタ後のレンズ一覧
  const [lensList2, setLensList2] = useState<Lens[]>([]);
  // 選択されているクエリタイプ
  const [queryType, setQueryType] = useState<string>('MaxWideFocalLength');
  // クエリに入力する値
  const [queryValue, setQueryValue] = useState<string>('');
  // クエリ一覧
  const [queryList, setQueryList] = useState<Query[]>([]);

  /** 起動時の読み込み */
  useEffect(() => {
    fetch('./lens_data.json').then(res => {
      if (res.ok) {
        res.json().then(data => {
          setLensList(data);
        });
      }
    });
  }, []);

  // 自動でフィルタしておく
  useEffect(() => {
    setLensList2(calcFilteredLensList(lensList, queryList));
  }, [lensList, queryList]);

  // クエリを追加する
  const addQuery = () => {
    // Boolean型な判定条件の場合
    if (BooleanQueryTypeList.includes(queryType)) {
      setQueryList([...queryList.filter(q => q.type.name !== queryType), createQuery(queryType, 0)]);
      return;
    }

    // 入力チェック
    const value = parseFloat2(queryValue);
    if (value === null) {
      window.alert('エラー：その条件では追加できません。');
      return;
    }

    // 入力
    if (MilliMeterToMeterQueryTypeList.includes(queryType)) {
      // 単位変換を伴う場合
      const temp = new Decimal(queryValue);
      const temp2 = temp.mul(new Decimal(1000));
      const value2 = temp2.toNumber();
      setQueryList([...queryList.filter(q => q.type.name !== queryType), createQuery(queryType, value2)]);
      return;
    }
    // 単位変換を伴わない場合
    setQueryList([...queryList.filter(q => q.type.name !== queryType), createQuery(queryType, value)]);
  };

  // クエリを削除する
  const deleteQuery = (queryType: string) => {
    setQueryList(queryList.filter(q => q.type.name !== queryType));
  };

  return (<Container>
    <Row className="my-3">
      <Col>
        <h1 className="text-center">レンズデータベース</h1>
      </Col>
    </Row>
    <Row className="my-3">
      <Col>
        <Form>
          <Form.Row>
            <Col xs="auto">
              <Form.Control as="select" value={queryType}
                onChange={e => setQueryType(e.currentTarget.value)}>
                {QueryTypeList.map(q => 
                  <option key={q.name} value={q.name}>{q.prefixMessage}</option>
                )}
              </Form.Control>
            </Col>
            {BooleanQueryTypeList.includes(queryType)
              ? <></>
              : <>
                <Col xs={2}>
                  <Form.Control value={queryValue} placeholder="数値を入力"
                    onChange={e => setQueryValue(e.currentTarget.value)} />
                </Col>
                <Col xs="auto">
                  <Form.Control as="select" value={queryType} readOnly>
                    {QueryTypeList.map(q =>
                      <option key={q.name} value={q.name}>{q.suffixMessage}</option>
                    )}
                  </Form.Control>
                </Col>
              </>}
            <Col xs="auto">
              <Button onClick={addQuery}>条件を追加</Button>
            </Col>
          </Form.Row>
        </Form>
      </Col>
    </Row>
    <Row className="my-3">
      <Col>
        {queryList.map(query => <QueryButton key={query.type.name} query={query} deleteQuery={() => deleteQuery(query.type.name)} />)}
      </Col>
    </Row>
    <Row className="my-3">
      <Col>
        <Table size="sm" striped>
          <thead>
            <tr>
              <th>メーカー</th>
              <th>レンズ名</th>
              <th>価格(税抜)</th>
            </tr>
          </thead>
          <tbody>
            {lensList2.map(lens => <tr key={lens.id}>
              <td>{lens.maker}</td>
              <td>{lens.name}</td>
              <td>{lens.price}</td>
            </tr>)}
          </tbody>
        </Table>
      </Col>
    </Row>
  </Container>);
}

export default App;
