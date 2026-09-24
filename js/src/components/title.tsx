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
        {/* A plain <a> to the index.html, not <Link to="/nightly-release/">:
            CloudFront does not resolve directory URLs to index.html (see #69),
            so only the full object key loads when fetched directly. */}
        <a href="/nightly-release/index.html">Nightly release status</a>
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
