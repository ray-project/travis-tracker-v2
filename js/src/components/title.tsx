import { Col, Row, Typography } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons"
import { Link } from "gatsby";
import React from "react";
import rayBugImg from "../static/ray-bug.png";

const Title: React.FC = () => (
  <Row justify="space-around" align="middle">
    <Col span={4}>
      <img src={rayBugImg} height="100px"></img>
    </Col>
    <Col span={8}>
      <Typography.Title level={1}>Ray Flakey Test Tracker
      </Typography.Title>
    </Col>
    <Col flex="auto"></Col>
    <Col span={2}>
      <Typography.Title level={3}>
        <Link to="https://anyscale-hq.notion.site/Public-Ray-Flaky-Test-Tracker-55b2edc397364b8ca8cbe3b26cbc6e1a">
          <InfoCircleOutlined></InfoCircleOutlined>
        </Link>
      </Typography.Title>
    </Col>
  </Row>
);

export default Title;
