import React from "react";
import favicon from "../static/favicon.ico";
import rayBugImg from "../static/ray-bug.png";
import { Helmet } from "react-helmet";
import { PageProps, Link, graphql } from "gatsby";
import { Typography, Row, Col, Layout, Popover, Space } from "antd";
import data from "../data.json";
import { SiteFailedTest } from "../interface";
import "./table.css";

const { Content } = Layout;

const failedTests = data as [SiteFailedTest];

export const query = graphql`
  {
    site {
      buildTime(formatString: "YYYY-MM-DD hh:mm a z")
    }
  }
`;

type DataProps = {
  site: {
    buildTime: string;
  };
};

const LayoutWrapper: React.FC = (props) => (
  <Layout style={{ backgroundColor: "white" }}>
    <Helmet>
      <link rel="icon" href={favicon}></link>
    </Helmet>
    <Content
      style={{
        padding: "5%",
        backgroundColor: "white",
        alignContent: "center",
      }}
    >
      {props.children}
    </Content>
  </Layout>
);

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

interface TableRowProp {
  data: SiteFailedTest;
}
const TableRow: React.FC<TableRowProp> = (props) => {
  const { name, status_segment_bar } = props.data;
  return (
    <tr>
      <th>
        {/* Trim the first two // */}
        {name.slice(2)}
      </th>
      {status_segment_bar.map(({ failed }) =>
        failed ? <td className="failed"></td> : <td className="success"></td>
      )}
    </tr>
  );
};

const TableGrid: React.FC = (props) => (
  // Table horizontal scroll with fixed header column
  // https://stackoverflow.com/a/14486644
  <div className="outer">
    <div className="inner">
      <table>
        {failedTests.map((f) => (
          <TableRow data={f}></TableRow>
        ))}
      </table>
    </div>
  </div>
);

const App: React.FC<PageProps<DataProps>> = ({ data, path }) => (
  <LayoutWrapper>
    <Title></Title>
    <TableGrid></TableGrid>
  </LayoutWrapper>
);

export default App;
