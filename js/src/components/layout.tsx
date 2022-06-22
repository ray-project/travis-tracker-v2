import { Layout } from "antd";
import React from "react";
import { Helmet } from "react-helmet";
import favicon from "../static/favicon.ico";

const { Content } = Layout;

const LayoutWrapper: React.FC = (props) => (
  <Layout style={{ backgroundColor: "white" }}>
    <Helmet>
      <link rel="icon" href={favicon}></link>
    </Helmet>
    <Content
      style={{
        padding: "4%",
        paddingTop: "0.5%",
        backgroundColor: "white",
        alignContent: "center",
      }}
    >
      {props.children}
    </Content>
  </Layout>
);

export default LayoutWrapper;
