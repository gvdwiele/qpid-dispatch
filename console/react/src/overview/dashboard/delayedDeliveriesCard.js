import React from "react";
import { Table, TableHeader, TableBody } from "@patternfly/react-table";

// update the table every 5 seconds
const UPDATE_INTERVAL = 1000 * 5;

class DelayedDeliveriesCard extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      lastUpdate: new Date(),
      columns: [
        "Router",
        "Connection",
        "1 sec rate",
        "10 sec rate",
        "Capacity",
        "Unsettled",
        ""
      ],
      rows: []
    };
    this.rates = {};
  }

  componentDidMount = () => {
    this.mounted = true;
    this.timer = setInterval(this.updateData, UPDATE_INTERVAL);
    this.updateData();
  };

  componentWillUnmount = () => {
    this.mounted = false;
    clearInterval(this.timer);
  };

  updateData = () => {
    let links = [];
    // send the requests for all connection and router info for all routers
    this.props.service.management.topology.fetchAllEntities(
      [{ entity: "router.link" }, { entity: "connection" }],
      nodes => {
        if (!this.mounted) return;
        for (let node in nodes) {
          let response = nodes[node]["router.link"];
          // eslint-disable-next-line no-loop-func
          response.results.forEach(result => {
            let link = this.props.service.utilities.flatten(
              response.attributeNames,
              result
            );
            if (link.linkType === "endpoint") {
              link.router = this.props.service.utilities.nameFromId(node);
              let connections = nodes[node]["connection"];
              connections.results.some(connection => {
                let conn = this.props.service.utilities.flatten(
                  connections.attributeNames,
                  connection
                );
                if (link.connectionId === conn.identity) {
                  link.connection = this.props.service.utilities.clientName(
                    conn
                  );
                  return true;
                }
                return false;
              });
              let delayedRates = this.props.service.utilities.rates(
                link,
                ["deliveriesDelayed1Sec", "deliveriesDelayed10Sec"],
                this.rates,
                link.name,
                12 // average over 12 snapshots (each snapshot is 5 seconds apart)
              );
              link.deliveriesDelayed1SecRate = Math.round(
                delayedRates.deliveriesDelayed1Sec,
                1
              );
              link.deliveriesDelayed10SecRate = Math.round(
                delayedRates.deliveriesDelayed10Sec,
                1
              );
              /* The killConnection event handler (in qdrOverview.js) expects
                 a row object with a routerId and the identity of a connection. 
                 Here we set those attributes so that when killConnection is 
                 called, it will kill the link's connection
              */
              link.routerId = node;
              link.identity = link.connectionId;

              links.push(link);
            }
          });
        }
        if (links.length === 0) return;
        // update the grid's data
        links = links.filter(link => {
          return (
            link.deliveriesDelayed1SecRate > 0 ||
            link.deliveriesDelayed10SecRate > 0
          );
        });
        links.sort((a, b) => {
          if (a.deliveriesDelayed1SecRate > b.deliveriesDelayed1SecRate)
            return -1;
          else if (a.deliveriesDelayed1SecRate < b.deliveriesDelayed1SecRate)
            return 1;
          else if (a.unsettledCount > b.unsettledCount) return -1;
          else if (a.unsettledCount < b.unsettledCount) return 1;
          else return 0;
        });
        // take top 5 records
        links.splice(5);
        let rows = links.map(link => {
          return [
            link.router,
            link.connection,
            link.deliveriesDelayed1SecRate.toLocaleString(),
            link.deliveriesDelayed10SecRate.toLocaleString(),
            link.capacity.toLocaleString(),
            link.unsettledCount.toLocaleString(),
            ""
          ];
        });
        this.setState({ rows, lastUpdate: new Date() });
      }
    );
  };

  nextUpdateString = () => {
    const nextUpdate = new Date(
      this.state.lastUpdate.getTime() + UPDATE_INTERVAL
    );
    return this.props.service.utilities.strDate(nextUpdate);
  };

  lastUpdateString = () => {
    return this.props.service.utilities.strDate(this.state.lastUpdate);
  };
  render() {
    const { columns, rows } = this.state;

    const caption = (
      <React.Fragment>
        <span className="caption">Links with delayed deliveries</span>
        <div className="updated">
          Updated at {this.lastUpdateString()} | Next {this.nextUpdateString()}
        </div>
      </React.Fragment>
    );
    return (
      <Table caption={caption} cells={columns} rows={rows}>
        <TableHeader />
        <TableBody />
      </Table>
    );
  }
}

export default DelayedDeliveriesCard;