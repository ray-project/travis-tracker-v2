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
    {/* The two pages are otherwise unreachable from one another: neither the
        layout nor the index carries navigation. Putting the link here means a
        page only has to render <Title /> to be part of the site. */}
    <Col span={4}>
      <Typography.Title level={5}>
        <Link to="/">Flaky tests</Link>
        {" · "}
        <Link to="/nightly-release/">Nightly release status</Link>
      </Typography.Title>
    </Col>
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
