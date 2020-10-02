import { Col, Row, Typography } from "antd";
import React from "react";
import rayBugImg from "../static/ray-bug.png";

const Title: React.FC = () => (
  <Row justify="space-around" align="middle">
    <Col>
      <img src={rayBugImg} height="100px"></img>
    </Col>
    <Col>
      <Typography.Title level={1}>Ray Flakey Test Tracker</Typography.Title>
    </Col>
  </Row>
);

export default Title;
